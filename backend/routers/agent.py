import json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from access_policy import current_lab_booking, lab_access_denial
from database import get_db
from device_registry import require_registered_device
from policy import (
    build_policy, find_matching_rule, get_policy_rules,
    sign_policy_snapshot, verify_policy_snapshot,
)
from routers.points import apply_point_event, mark_due_no_shows
from routers.users import get_current_user
from time_utils import as_utc, as_lab_naive, lab_now_naive, utc_now
from utils import normalize_email
from url_policy import normalize_domain

router = APIRouter(tags=["Hardware Agent"])
optional_agent_oauth2 = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

STALE_SESSION_AFTER = timedelta(minutes=2)
MAX_IDEMPOTENCY_KEY_LENGTH = 128
MAX_USAGE_BATCH_SIZE = 100
VALID_END_REASONS = {
    "logout",
    "violation",
    "stale_cleanup",
    "shutdown",
    "error",
    "admin",
}
@router.get("/agent/policy")
def get_agent_policy(db: Session = Depends(get_db)):
    """Return the active, versioned policy used by Windows Agents."""

    policy = build_policy(get_policy_rules(db))
    return {**policy, "policy_token": sign_policy_snapshot(policy)}


def _clean_device_mac(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip().lower()
    return cleaned or None


def _clean_idempotency_key(value: Optional[str], field_name: str) -> Optional[str]:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise HTTPException(status_code=422, detail=f"{field_name} is too long.")
    return cleaned


def _same_session_identity(
    access_log,
    user_id,
    lab_id,
    device_mac,
    lab_device_id=None,
) -> bool:
    return (
        access_log.user_id == user_id
        and access_log.lab_id == lab_id
        and _clean_device_mac(access_log.device_mac) == device_mac
        and (
            access_log.lab_device_id is None
            or access_log.lab_device_id == lab_device_id
        )
    )


def _cleanup_stale_sessions(db: Session) -> int:
    """Close sessions whose Agent has stopped sending heartbeats."""
    now_utc = utc_now()
    stale_before_utc = now_utc - STALE_SESSION_AFTER

    stale_filter = db.query(models.LabAccessLog).filter(
        models.LabAccessLog.session_status == "active",
        models.LabAccessLog.exit_time.is_(None),
        or_(
            and_(
                models.LabAccessLog.last_heartbeat_at.is_not(None),
                models.LabAccessLog.last_heartbeat_at < stale_before_utc,
            ),
            and_(
                models.LabAccessLog.last_heartbeat_at.is_(None),
                models.LabAccessLog.entry_time < stale_before_utc,
            ),
        ),
    )
    return stale_filter.update(
        {
            models.LabAccessLog.session_status: "abandoned",
            models.LabAccessLog.end_reason: "stale_cleanup",
            models.LabAccessLog.exit_time: now_utc,
        },
        synchronize_session=False,
    )


def _require_active_session(access_log: models.LabAccessLog) -> None:
    if access_log.session_status != "active" or access_log.exit_time is not None:
        raise HTTPException(status_code=409, detail="Session is no longer active.")


def _get_optional_agent_user(
    token: Optional[str] = Depends(optional_agent_oauth2),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    if not token:
        return None
    try:
        return get_current_user(token, db)
    except HTTPException as exc:
        if exc.status_code in {401, 404}:
            return None
        raise


def _require_session_device(
    db: Session,
    access_log: models.LabAccessLog,
    device_id: Optional[str],
    device_token: Optional[str],
    current_user: Optional[models.User] = None,
) -> models.LabDevice:
    registered_device = require_registered_device(db, device_id, device_token)
    if access_log.lab_device_id is not None:
        if registered_device.id != access_log.lab_device_id:
            raise HTTPException(status_code=403, detail="Workstation is not authorized for this session.")
        return registered_device

    # Compatibility for sessions created before device registration became
    # mandatory: require both the authenticated owner and the matching Lab
    # workstation. New sessions are always bound to lab_device_id.
    session_mac = _clean_device_mac(access_log.device_mac)
    registered_mac = _clean_device_mac(registered_device.device_mac)
    if (
        current_user is None
        or current_user.id != access_log.user_id
        or registered_device.lab_id != access_log.lab_id
        or not session_mac
        or session_mac != registered_mac
    ):
        raise HTTPException(
            status_code=403,
            detail="Workstation and authenticated user are not authorized for this session.",
        )
    return registered_device


def _bind_recovered_session_device(
    db: Session,
    access_log: models.LabAccessLog,
    registered_device: models.LabDevice,
) -> None:
    if access_log.lab_device_id is not None:
        if access_log.lab_device_id != registered_device.id:
            raise HTTPException(status_code=409, detail="Session belongs to another workstation.")
        return

    if (
        access_log.lab_id != registered_device.lab_id
        or _clean_device_mac(access_log.device_mac)
        != _clean_device_mac(registered_device.device_mac)
    ):
        raise HTTPException(
            status_code=409,
            detail="Legacy session cannot be recovered from this workstation.",
        )
    access_log.lab_device_id = registered_device.id
    db.commit()


def _parse_usage_time(value: Optional[str], fallback: datetime) -> datetime:
    """Parse an Agent timestamp as UTC while accepting legacy local payloads."""
    if not value:
        return as_utc(fallback)

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid usage timestamp.") from exc

    # New Agents send an explicit UTC offset. Older Agents sent naive Lab local
    # time; as_utc() preserves those events by assuming UTC+7 for naive values.
    return as_utc(parsed)


@router.post("/agent/start-session")
def start_session(
    email: str = Form(...),
    lab_code: Optional[str] = Form(None),
    device: str = Form(...),
    device_mac: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    device_token: Optional[str] = Form(None),
    agent_version: Optional[str] = Form(None),
    client_session_id: Optional[str] = Form(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_email = normalize_email(email)
    if normalized_email != normalize_email(current_user.email):
        raise HTTPException(status_code=403, detail="Authenticated user does not match session user.")
    user = current_user

    denial = lab_access_denial(db, user.id, now=utc_now())
    if denial is not None:
        raise HTTPException(status_code=403, detail=denial[1])

    registered_device = require_registered_device(db, device_id, device_token)
    lab = db.query(models.Lab).filter(
        models.Lab.id == registered_device.lab_id,
    ).first()

    if not lab:
        raise HTTPException(status_code=404, detail="Assigned Lab not found.")
    if lab.status != "active":
        raise HTTPException(status_code=409, detail="Assigned Lab is not active.")

    if _cleanup_stale_sessions(db):
        # Persist stale-session cleanup before any recovery response. Without
        # this commit, an early return below could roll the cleanup back.
        db.commit()

    mark_due_no_shows(db)

    # Reconciliation can itself impose a ban. Check again before recovery too.
    denial = lab_access_denial(db, user.id, now=utc_now())
    if denial is not None:
        raise HTTPException(status_code=403, detail=denial[1])

    lab_now = lab_now_naive()
    current_booking = current_lab_booking(db, user.id, lab.id, lab_now)
    if current_booking is None:
        raise HTTPException(
            status_code=403,
            detail="An active Lab booking is required to start an Agent session.",
        )

    resolved_device_name = (device or "").strip() or None
    resolved_device_mac = _clean_device_mac(device_mac)
    if not resolved_device_name:
        raise HTTPException(status_code=422, detail="device is required.")
    if not resolved_device_mac:
        raise HTTPException(status_code=422, detail="device_mac is required.")

    resolved_lab_device_id = registered_device.id

    resolved_client_session_id = _clean_idempotency_key(
        client_session_id,
        "client_session_id",
    )

    if resolved_client_session_id:
        existing_request = db.query(models.LabAccessLog).filter(
            models.LabAccessLog.client_session_id == resolved_client_session_id,
        ).first()
        if existing_request:
            if existing_request.session_status == "active" and existing_request.exit_time is None:
                if _same_session_identity(
                    existing_request,
                    user.id,
                    lab.id,
                    resolved_device_mac,
                    resolved_lab_device_id,
                ) and existing_request.booking_id == current_booking.id:
                    _bind_recovered_session_device(db, existing_request, registered_device)
                    return {"session_id": existing_request.id, "recovered": True}
                raise HTTPException(
                    status_code=409,
                    detail="Client session key belongs to another active session.",
                )
            raise HTTPException(
                status_code=409,
                detail="Session request is already closed.",
            )

    active_user_session = db.query(models.LabAccessLog).filter(
        models.LabAccessLog.user_id == user.id,
        models.LabAccessLog.session_status == "active",
        models.LabAccessLog.exit_time.is_(None),
    ).first()
    if active_user_session:
        # Recover an orphaned active row when the original response was lost.
        # A different lab or device remains a real conflict.
        if _same_session_identity(
            active_user_session,
            user.id,
            lab.id,
            resolved_device_mac,
            resolved_lab_device_id,
        ) and active_user_session.booking_id == current_booking.id:
            _bind_recovered_session_device(db, active_user_session, registered_device)
            return {"session_id": active_user_session.id, "recovered": True}
        raise HTTPException(
            status_code=409,
            detail="This user already has an active lab session.",
        )

    active_device_query = db.query(models.LabAccessLog).filter(
        models.LabAccessLog.session_status == "active",
        models.LabAccessLog.exit_time.is_(None),
    )
    if resolved_lab_device_id:
        active_device_query = active_device_query.filter(
            or_(
                models.LabAccessLog.lab_device_id == resolved_lab_device_id,
                func.lower(func.trim(models.LabAccessLog.device_mac)) == resolved_device_mac,
            ),
        )
    else:
        active_device_query = active_device_query.filter(
            func.lower(func.trim(models.LabAccessLog.device_mac)) == resolved_device_mac,
        )
    active_device_session = active_device_query.first()
    if active_device_session:
        raise HTTPException(
            status_code=409,
            detail="This device already has an active lab session.",
        )

    registered_device.device_name = resolved_device_name
    registered_device.device_mac = resolved_device_mac
    registered_device.agent_version = (agent_version or "").strip()[:64] or registered_device.agent_version
    registered_device.last_seen_at = utc_now()

    now_utc = utc_now()
    if current_booking.status != "reserved":
        raise HTTPException(
            status_code=403,
            detail="A reserved Lab booking is required to start a new Agent session.",
        )
    current_booking.status = "attended"
    current_booking.checked_in_at = now_utc

    new_log = models.LabAccessLog(
        lab_id=lab.id,
        user_id=user.id,
        lab_device_id=resolved_lab_device_id,
        booking_id=current_booking.id,
        entry_time=now_utc,
        access_type="manual",
        status="success",
        device_used=resolved_device_name,
        device_mac=resolved_device_mac,
        client_session_id=resolved_client_session_id,
        session_status="active",
        last_heartbeat_at=now_utc,
    )
    try:
        db.add(new_log)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if resolved_client_session_id:
            registered_device = require_registered_device(db, device_id, device_token)
            fresh_lab = db.get(models.Lab, registered_device.lab_id)
            fresh_booking = current_lab_booking(db, user.id, registered_device.lab_id, lab_now_naive())
            recovered_session = db.query(models.LabAccessLog).filter(
                models.LabAccessLog.client_session_id == resolved_client_session_id,
                models.LabAccessLog.session_status == "active",
                models.LabAccessLog.exit_time.is_(None),
            ).first()
            if (
                recovered_session and fresh_lab and fresh_lab.status == "active"
                and fresh_booking and recovered_session.booking_id == fresh_booking.id
                and lab_access_denial(db, user.id, now=utc_now()) is None
                and registered_device.lab_id == lab.id
                and _same_session_identity(
                    recovered_session,
                    user.id,
                    lab.id,
                    resolved_device_mac,
                    resolved_lab_device_id,
                )
            ):
                _bind_recovered_session_device(db, recovered_session, registered_device)
                return {"session_id": recovered_session.id, "recovered": True}
        raise HTTPException(
            status_code=409,
            detail="This user or device already has an active lab session.",
        ) from exc
    db.refresh(new_log)
    return {"session_id": new_log.id}


@router.post("/agent/log-usage")
def log_usage(
    session_id: int = Form(...),
    usage_data: str = Form(...),
    device_id: Optional[str] = Form(None),
    device_token: Optional[str] = Form(None),
    current_user: Optional[models.User] = Depends(_get_optional_agent_user),
    db: Session = Depends(get_db),
):
    access_log = db.query(models.LabAccessLog).filter(
        models.LabAccessLog.id == session_id
    ).first()
    if not access_log:
        raise HTTPException(status_code=404, detail="Session not found.")
    _require_session_device(db, access_log, device_id, device_token, current_user)

    try:
        logs = json.loads(usage_data)
        if not isinstance(logs, list):
            raise HTTPException(status_code=422, detail="usage_data must be a JSON list.")
        if len(logs) > MAX_USAGE_BATCH_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"A usage batch cannot contain more than {MAX_USAGE_BATCH_SIZE} items.",
            )

        now = utc_now()
        parsed_logs = []
        for item in logs:
            if not isinstance(item, dict) or not str(item.get("name", "")).strip():
                raise HTTPException(status_code=422, detail="Each usage item needs a name.")

            event_id = _clean_idempotency_key(item.get("event_id"), "event_id")

            usage_start = _parse_usage_time(item.get("started_at"), now)
            usage_end = _parse_usage_time(item.get("ended_at"), usage_start)
            if usage_end < usage_start:
                raise HTTPException(
                    status_code=422,
                    detail="Usage end time cannot be before start time.",
                )

            try:
                duration = max(0, int(item.get("duration", 0)))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail="Invalid usage duration.") from exc

            # Old Agents only sent a total duration. New Agents send timestamps
            # as well; calculate a duration when it was omitted or zero.
            if duration == 0 and usage_end > usage_start:
                duration = int((usage_end - usage_start).total_seconds())

            parsed_logs.append({
                "event_id": event_id,
                "program_name": str(item["name"]).strip(),
                "duration_seconds": duration,
                "usage_start_time": usage_start,
                "usage_end_time": usage_end,
            })

        # New Agents use event_id, so queued events can be delivered after a
        # timeout or after stale cleanup. Legacy requests without event_id
        # still require an active session for backward compatibility.
        session_is_active = (
            access_log.session_status == "active"
            and access_log.exit_time is None
        )
        if not session_is_active and not all(item["event_id"] for item in parsed_logs):
            _require_active_session(access_log)

        created_count = 0
        duplicate_count = 0
        for item in parsed_logs:
            event_id = item["event_id"]
            if event_id:
                existing = db.query(models.ProgramUsageLog).filter(
                    models.ProgramUsageLog.event_id == event_id,
                ).first()
                if existing:
                    if existing.lab_access_log_id != session_id:
                        raise HTTPException(
                            status_code=409,
                            detail="Usage event belongs to another session.",
                        )
                    duplicate_count += 1
                    continue

            db.add(models.ProgramUsageLog(
                lab_access_log_id=session_id,
                program_name=item["program_name"],
                duration_seconds=item["duration_seconds"],
                usage_start_time=item["usage_start_time"],
                usage_end_time=item["usage_end_time"],
                event_id=event_id,
            ))
            created_count += 1

        db.commit()
        return {
            "message": "Data logged successfully.",
            "count": len(logs),
            "created_count": created_count,
            "duplicate_count": duplicate_count,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/log-violation")
def log_violation(
    session_id: int = Form(...),
    program_name: str = Form(...),
    reason: Optional[str] = Form(None),
    action_taken: str = Form("logout"),
    event_id: Optional[str] = Form(None),
    process_name: Optional[str] = Form(None),
    exe_path: Optional[str] = Form(None),
    window_title: Optional[str] = Form(None),
    detection_source: Optional[str] = Form(None),
    detected_at: Optional[str] = Form(None),
    policy_version: Optional[str] = Form(None),
    policy_token: Optional[str] = Form(None),
    executable_identity: Optional[str] = Form(None),
    browser_domain: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    device_token: Optional[str] = Form(None),
    current_user: Optional[models.User] = Depends(_get_optional_agent_user),
    db: Session = Depends(get_db),
):
    access_log = db.query(models.LabAccessLog).filter(
        models.LabAccessLog.id == session_id
    ).first()
    if not access_log:
        raise HTTPException(status_code=404, detail="Session not found.")
    _require_session_device(db, access_log, device_id, device_token, current_user)

    cleaned_program_name = program_name.strip()
    if not cleaned_program_name:
        raise HTTPException(status_code=422, detail="program_name is required.")
    if browser_domain is not None:
        domain = normalize_domain(browser_domain)
        if not domain or domain != browser_domain or detection_source != "browser_domain":
            raise HTTPException(status_code=422, detail="A canonical browser domain is required.")
        cleaned_program_name = domain
        window_title = None
    elif detection_source == "browser_domain":
        raise HTTPException(status_code=422, detail="browser_domain is required.")

    resolved_event_id = _clean_idempotency_key(event_id, "event_id")
    if resolved_event_id:
        existing = db.query(models.UsageViolation).filter(
            models.UsageViolation.event_id == resolved_event_id,
        ).first()
        if existing:
            if existing.lab_access_log_id != session_id:
                raise HTTPException(
                    status_code=409,
                    detail="Violation event belongs to another session.",
                )
            return {
                "message": "Violation already logged.",
                "violation_id": existing.id,
            }

    identity = {}
    if executable_identity:
        try:
            if len(executable_identity) > 4096:
                raise ValueError("Identity too large.")
            identity = json.loads(executable_identity)
            if not isinstance(identity, dict) or any(
                key not in {"original_filename", "internal_name", "product_name", "company_name"}
                or not isinstance(value, str) or len(value) > 256
                for key, value in identity.items()
            ):
                raise ValueError("Invalid identity.")
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="Invalid executable identity.") from exc
    if not any(identity.get(key, "").strip() for key in (
        "original_filename", "internal_name", "product_name",
    )):
        # Acknowledge obsolete outbox entries without applying title/name-only penalties.
        return {"message": "Unverified violation ignored.", "ignored": True,
                "reason": "executable_identity_required"}

    received_at = utc_now()
    event_time = _parse_usage_time(detected_at, received_at)
    clock_tolerance = timedelta(minutes=5)
    if detected_at and (
        event_time < as_utc(access_log.entry_time) - clock_tolerance
        or event_time > received_at + clock_tolerance
    ):
        raise HTTPException(status_code=422, detail="Detection time is outside the session window.")

    if policy_token:
        if not detected_at:
            raise HTTPException(status_code=422, detail="A signed policy requires detected_at.")
        try:
            event_policy = verify_policy_snapshot(policy_token)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid policy snapshot.") from exc
        if (
            policy_version != event_policy["version"]
            or event_policy["issued_at"] > event_time.timestamp() + clock_tolerance.total_seconds()
        ):
            raise HTTPException(status_code=422, detail="Policy snapshot does not match the event.")
    else:
        # Legacy Agents have no signed receipt; keep validating their evidence
        # against the active rules rather than trusting client-supplied history.
        event_policy = build_policy(get_policy_rules(db))
    matched_rule = find_matching_rule(
        event_policy["data"],
        process_name=(process_name or cleaned_program_name).strip(),
        exe_path=exe_path,
        window_title=window_title,
        executable_identity=identity,
        browser_domain=browser_domain,
    )
    if matched_rule is None:
        raise HTTPException(
            status_code=422,
            detail="Violation does not match the supplied or active blacklist policy.",
        )

    session_is_active = (
        access_log.session_status == "active"
        and access_log.exit_time is None
    )
    if not session_is_active and not resolved_event_id:
        _require_active_session(access_log)

    violation = models.UsageViolation(
        lab_access_log_id=session_id,
        program_name=cleaned_program_name,
        reason=reason.strip() if reason else None,
        action_taken=action_taken.strip() or "logout",
        detected_at=event_time,
        event_id=resolved_event_id,
        process_name=process_name.strip() if process_name else None,
        exe_path=exe_path.strip() if exe_path else None,
        window_title=window_title.strip() if window_title else None,
        detection_source=detection_source.strip() if detection_source else None,
        policy_version=event_policy["version"],
        matched_rule_id=matched_rule.get("id"),
    )
    point_result = None
    try:
        db.add(violation)
        db.flush()
        point_event_id = f"violation:{resolved_event_id or violation.id}"
        point_result = apply_point_event(
            access_log.user_id,
            "forbidden_app",
            db,
            note=f"ตรวจพบ{'เว็บไซต์' if browser_domain else 'โปรแกรม'}ต้องห้าม: {cleaned_program_name}",
            event_id=point_event_id,
            source_type="usage_violation",
            source_id=violation.id,
            effective_at=violation.detected_at,
            commit=False,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if resolved_event_id:
            existing = db.query(models.UsageViolation).filter(
                models.UsageViolation.event_id == resolved_event_id,
            ).first()
            if existing and existing.lab_access_log_id == session_id:
                return {
                    "message": "Violation already logged.",
                    "violation_id": existing.id,
                }
        raise HTTPException(status_code=409, detail="Duplicate violation event.") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to record violation and points.") from exc
    db.refresh(violation)
    return {
        "message": "Violation logged successfully.",
        "violation_id": violation.id,
        "points": point_result,
    }


@router.post("/agent/heartbeat")
def heartbeat(
    session_id: int = Form(...),
    device_mac: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    device_token: Optional[str] = Form(None),
    current_user: Optional[models.User] = Depends(_get_optional_agent_user),
    db: Session = Depends(get_db),
):
    access_log = db.query(models.LabAccessLog).filter(
        models.LabAccessLog.id == session_id
    ).populate_existing().with_for_update().first()
    if not access_log:
        raise HTTPException(status_code=404, detail="Session not found.")

    _require_active_session(access_log)
    registered_device = _require_session_device(
        db, access_log, device_id, device_token, current_user,
    )
    registered_device.last_seen_at = utc_now()

    reported_mac = _clean_device_mac(device_mac)
    stored_mac = _clean_device_mac(access_log.device_mac)
    if reported_mac and stored_mac and reported_mac != stored_mac:
        raise HTTPException(status_code=409, detail="Device does not match session.")

    heartbeat_at = utc_now()
    denial = lab_access_denial(db, access_log.user_id, now=heartbeat_at)
    lab = db.get(models.Lab, access_log.lab_id)
    booking = current_lab_booking(db, access_log.user_id, access_log.lab_id, as_lab_naive(heartbeat_at))
    lab_allowed = lab is not None and lab.status == "active" and registered_device.lab_id == access_log.lab_id
    if denial or not lab_allowed or booking is None or booking.id != access_log.booking_id:
        session_booking = access_log.booking
        if (
            not denial and lab_allowed and session_booking is not None
            and session_booking.status == "attended"
            and datetime.combine(session_booking.booking_date, session_booking.end_time) <= as_lab_naive(heartbeat_at)
        ):
            # A normal booking expiry keeps the existing completion reward and
            # its idempotent event ID. Revocation below never grants a reward.
            end_session(session_id, "logout", device_id, device_token, current_user, db)
            raise HTTPException(status_code=409, detail="Session booking has ended.")
        # Older Agents already return to Login on 409. Keep durable telemetry
        # upload/end-session available, but never award completion points for a
        # session whose access has been withdrawn.
        access_log.session_status = "completed"
        access_log.end_reason = "access_revoked"
        access_log.exit_time = heartbeat_at
        if access_log.booking and access_log.booking.status in {"reserved", "attended"}:
            access_log.booking.status = "completed"
            access_log.booking.checked_out_at = heartbeat_at
        db.commit()
        raise HTTPException(status_code=409, detail="Session access is no longer available.")
    access_log.last_heartbeat_at = heartbeat_at
    db.commit()
    return {
        "message": "Heartbeat accepted.",
        "session_id": session_id,
        "last_heartbeat_at": heartbeat_at,
    }


@router.post("/agent/end-session")
def end_session(
    session_id: int = Form(...),
    end_reason: str = Form("logout"),
    device_id: Optional[str] = Form(None),
    device_token: Optional[str] = Form(None),
    current_user: Optional[models.User] = Depends(_get_optional_agent_user),
    db: Session = Depends(get_db),
):
    access_log = db.query(models.LabAccessLog).filter(
        models.LabAccessLog.id == session_id
    ).with_for_update().first()
    if not access_log:
        raise HTTPException(status_code=404, detail="Session not found.")
    _require_session_device(db, access_log, device_id, device_token, current_user)

    cleaned_reason = (end_reason or "logout").strip().lower()
    if cleaned_reason not in VALID_END_REASONS:
        raise HTTPException(status_code=422, detail="Invalid session end reason.")

    was_active = access_log.session_status == "active" and access_log.exit_time is None
    changed = False
    point_result = None
    if access_log.exit_time is None:
        access_log.exit_time = utc_now()
        changed = True

    if access_log.session_status == "active":
        access_log.session_status = (
            "abandoned" if cleaned_reason == "stale_cleanup" else "completed"
        )
        access_log.end_reason = cleaned_reason
        changed = True

    if was_active and changed:
        booking = access_log.booking
        if booking:
            booking.checked_out_at = access_log.exit_time
            if booking.status in {"reserved", "attended"}:
                booking.status = "completed"
                if not booking.checked_in_at:
                    booking.checked_in_at = access_log.entry_time

        if cleaned_reason in {"logout", "shutdown"}:
            point_result = apply_point_event(
                access_log.user_id,
                "complete_session",
                db,
                note=f"จบการใช้งานห้องจาก session #{access_log.id}",
                event_id=f"session:{access_log.id}:complete",
                source_type="lab_access_log",
                source_id=access_log.id,
                effective_at=access_log.exit_time,
                commit=False,
            )

    if changed:
        db.commit()

    return {
        "message": "Session ended successfully.",
        "session_id": session_id,
        "session_status": access_log.session_status,
        "end_reason": access_log.end_reason,
        "points": point_result,
    }
