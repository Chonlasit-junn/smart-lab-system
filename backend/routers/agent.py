import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session

import models
from database import get_db

router = APIRouter(tags=["Hardware Agent"])


def _parse_usage_time(value: Optional[str], fallback: datetime) -> datetime:
    """Parse an Agent timestamp while keeping compatibility with old payloads."""
    if not value:
        return fallback

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid usage timestamp.") from exc

    # The current Supabase columns are timestamp without time zone. Normalize an
    # explicitly supplied offset before storing it in those columns.
    if parsed.tzinfo:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


@router.post("/agent/start-session")
def start_session(
    email: str = Form(...),
    lab_code: str = Form(...),
    device: str = Form(...),
    device_mac: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.email == email).first()
    lab = db.query(models.Lab).filter(models.Lab.code == lab_code).first()

    if not user or not lab:
        raise HTTPException(status_code=404, detail="Invalid credentials.")

    resolved_device_name = device.strip() or None
    resolved_device_mac = (device_mac or "").strip() or None

    new_log = models.LabAccessLog(
        lab_id=lab.id,
        user_id=user.id,
        entry_time=datetime.now(),
        access_type="manual",
        status="success",
        device_used=resolved_device_name,
        device_mac=resolved_device_mac,
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return {"session_id": new_log.id}


@router.post("/agent/log-usage")
def log_usage(
    session_id: int = Form(...),
    usage_data: str = Form(...),
    device_name: Optional[str] = Form(None),
    device_mac: Optional[str] = Form(None),
    # Backward-compatible names used by the unmerged Agent refactor.
    device: Optional[str] = Form(None),
    mac: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    access_log = db.query(models.LabAccessLog).filter(
        models.LabAccessLog.id == session_id
    ).first()
    if not access_log:
        raise HTTPException(status_code=404, detail="Session not found.")

    try:
        logs = json.loads(usage_data)
        now = datetime.now()
        # Keep accepting legacy payload fields while using the Session as the
        # canonical source for device identity.
        resolved_device_name = (
            device_name or device or access_log.device_used or ""
        ).strip() or None
        resolved_device_mac = (
            device_mac or mac or access_log.device_mac or ""
        ).strip() or None

        if not isinstance(logs, list):
            raise HTTPException(status_code=422, detail="usage_data must be a JSON list.")

        for item in logs:
            if not isinstance(item, dict) or not str(item.get("name", "")).strip():
                raise HTTPException(status_code=422, detail="Each usage item needs a name.")

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

            db.add(models.ProgramUsageLog(
                lab_access_log_id=session_id,
                program_name=str(item["name"]).strip(),
                duration_seconds=duration,
                usage_start_time=usage_start,
                usage_end_time=usage_end,
                device_name=resolved_device_name,
                device_mac=resolved_device_mac,
            ))

        db.commit()
        return {"message": "Data logged successfully.", "count": len(logs)}
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
    db: Session = Depends(get_db),
):
    access_log = db.query(models.LabAccessLog).filter(
        models.LabAccessLog.id == session_id
    ).first()
    if not access_log:
        raise HTTPException(status_code=404, detail="Session not found.")

    cleaned_program_name = program_name.strip()
    if not cleaned_program_name:
        raise HTTPException(status_code=422, detail="program_name is required.")

    violation = models.UsageViolation(
        lab_access_log_id=session_id,
        program_name=cleaned_program_name,
        reason=reason.strip() if reason else None,
        action_taken=action_taken.strip() or "logout",
        detected_at=datetime.now(),
    )
    db.add(violation)
    db.commit()
    db.refresh(violation)
    return {"message": "Violation logged successfully.", "violation_id": violation.id}


@router.post("/agent/end-session")
def end_session(
    session_id: int = Form(...),
    db: Session = Depends(get_db),
):
    access_log = db.query(models.LabAccessLog).filter(
        models.LabAccessLog.id == session_id
    ).first()
    if not access_log:
        raise HTTPException(status_code=404, detail="Session not found.")

    if access_log.exit_time is None:
        access_log.exit_time = datetime.now()
        db.commit()

    return {"message": "Session ended successfully.", "session_id": session_id}
