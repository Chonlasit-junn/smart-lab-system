from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
from database import get_db
from routers.users import get_current_user

router = APIRouter(tags=["Point System"])

MAX_POINTS = 100
BOOKING_MIN_POINTS = 80
NO_SHOW_GRACE = timedelta(minutes=15)
MAX_EVENT_ID_LENGTH = 256

# ── กฎการเปลี่ยนคะแนน ────────────────────────────────────────────────────────
POINT_RULES = {
    "no_show": -5,          # จองแล้วไม่มา
    "forbidden_app": -10,   # เปิดโปรแกรมต้องห้ามในแล็บ
    "late_cancel": -3,      # ยกเลิกก่อนเวลา < 1 ชม.
    "complete_session": +1, # จบ session ปกติ
}

# ตรวจจาก threshold ต่ำสุดก่อน เพื่อให้ 10 คะแนนได้ Ban 30 วัน ไม่ใช่ 1 วัน
BAN_RULES = [
    {"below": 20, "ban_days": 30},
    {"below": 40, "ban_days": 7},
    {"below": 60, "ban_days": 3},
    {"below": 80, "ban_days": 1},
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _as_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def _clamp_score(value: Optional[int]) -> int:
    return min(MAX_POINTS, max(0, int(value if value is not None else MAX_POINTS)))


def _clean_event_id(value: Optional[str]) -> Optional[str]:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_EVENT_ID_LENGTH:
        raise ValueError("event_id is too long")
    return cleaned


def is_admin_user(user_id: int, db: Session) -> bool:
    return db.query(models.Role.id).join(
        models.UserRole,
        models.UserRole.role_id == models.Role.id,
    ).filter(
        models.UserRole.user_id == user_id,
        models.Role.name == "admin",
    ).first() is not None


def _require_user_access(
    target_user_id: int,
    current_user: models.User,
    db: Session,
) -> None:
    if current_user.id != target_user_id and not is_admin_user(current_user.id, db):
        raise HTTPException(status_code=403, detail="You cannot view another user's points.")


def get_or_create_points(user_id: int, db: Session) -> models.UserPoints:
    """ดึงบัญชีคะแนนและสร้างด้วย 100 คะแนนเมื่อเป็น user legacy"""
    record = db.query(models.UserPoints).filter(
        models.UserPoints.user_id == user_id,
    ).with_for_update().first()
    if not record:
        record = models.UserPoints(user_id=user_id, points=MAX_POINTS)
        db.add(record)
        db.flush()
    return record


def get_or_create_daily_score(
    user_id: int,
    score_date: date,
    db: Session,
) -> models.UserDailyScore:
    record = db.query(models.UserDailyScore).filter(
        models.UserDailyScore.user_id == user_id,
        models.UserDailyScore.score_date == score_date,
    ).with_for_update().first()
    if not record:
        record = models.UserDailyScore(
            user_id=user_id,
            score_date=score_date,
            score=MAX_POINTS,
        )
        db.add(record)
        db.flush()
    return record


def _get_active_ban(user_id: int, db: Session) -> Optional[models.BanRecord]:
    return db.query(models.BanRecord).filter(
        models.BanRecord.user_id == user_id,
        models.BanRecord.ban_until > _now_utc(),
    ).order_by(models.BanRecord.ban_until.desc()).first()


def apply_ban_if_needed(user_id: int, points: int, db: Session) -> Optional[int]:
    """สร้างประวัติ Ban เฉพาะเมื่อ Ban ใหม่ยาวกว่าที่กำลังใช้อยู่"""
    ban_days = next(
        (rule["ban_days"] for rule in sorted(BAN_RULES, key=lambda item: item["below"])
         if points < rule["below"]),
        None,
    )
    if ban_days is None:
        return None

    proposed_until = _now_utc() + timedelta(days=ban_days)
    active_ban = _get_active_ban(user_id, db)
    active_until = _as_aware(active_ban.ban_until) if active_ban else None
    remaining = active_until - _now_utc() if active_until else None
    if active_until is None or remaining < timedelta(days=ban_days) - timedelta(minutes=1):
        db.add(models.BanRecord(
            user_id=user_id,
            ban_until=proposed_until,
            reason=f"คะแนนต่ำกว่าเกณฑ์ ({points} คะแนน)",
        ))
    return ban_days


def is_user_banned(user_id: int, db: Session) -> Optional[datetime]:
    """คืนเวลาสิ้นสุด Ban ที่ยังมีผลอยู่นานที่สุด"""
    active_ban = _get_active_ban(user_id, db)
    return active_ban.ban_until if active_ban else None


def apply_point_event(
    user_id: int,
    reason: str,
    db: Session,
    note: Optional[str] = None,
    event_id: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
    effective_at: Optional[datetime] = None,
    commit: bool = True,
) -> dict:
    """Apply one idempotent point event to total and daily balances.

    ``commit=False`` lets Agent/session workflows commit the audit row and
    point event atomically in one transaction.
    """
    change = POINT_RULES.get(reason)
    if change is None:
        raise ValueError(f"Unknown reason: {reason}")

    resolved_event_id = _clean_event_id(event_id)
    if resolved_event_id:
        existing = db.query(models.PointLog).filter(
            models.PointLog.event_id == resolved_event_id,
        ).first()
        if existing:
            if existing.user_id != user_id or existing.reason != reason:
                raise ValueError("event_id is already associated with another point event")
            ban_until = is_user_banned(user_id, db)
            return {
                "before": existing.points_before,
                "after": existing.points_after,
                "change": existing.change,
                "daily_score_before": existing.daily_score_before,
                "daily_score_after": existing.daily_score_after,
                "score_date": existing.score_date,
                "ban_days": None,
                "ban_until": ban_until,
                "event_id": resolved_event_id,
                "idempotent": True,
            }

    if not db.query(models.User.id).filter(models.User.id == user_id).first():
        raise ValueError(f"User {user_id} not found")

    record = get_or_create_points(user_id, db)
    before = _clamp_score(record.points)
    after = _clamp_score(before + change)
    record.points = after
    record.updated_at = _now_utc()

    event_time = _as_aware(effective_at) or _now_utc()
    score_date = event_time.date()
    daily_record = get_or_create_daily_score(user_id, score_date, db)
    daily_before = _clamp_score(daily_record.score)
    daily_after = _clamp_score(daily_before + change)
    daily_record.score = daily_after
    daily_record.updated_at = event_time

    point_log = models.PointLog(
        user_id=user_id,
        change=change,
        reason=reason,
        note=note,
        event_id=resolved_event_id,
        source_type=source_type,
        source_id=source_id,
        points_before=before,
        points_after=after,
        daily_score_before=daily_before,
        daily_score_after=daily_after,
        score_date=score_date,
        created_at=event_time,
    )
    db.add(point_log)
    ban_days = apply_ban_if_needed(user_id, after, db)

    if commit:
        db.commit()
    else:
        db.flush()

    return {
        "before": before,
        "after": after,
        "change": change,
        "daily_score_before": daily_before,
        "daily_score_after": daily_after,
        "score_date": score_date,
        "ban_days": ban_days,
        "ban_until": is_user_banned(user_id, db),
        "event_id": resolved_event_id,
        "idempotent": False,
    }


def deduct_points(
    user_id: int,
    reason: str,
    db: Session,
    note: Optional[str] = None,
) -> dict:
    """Backward-compatible wrapper for internal callers and manual tests."""
    return apply_point_event(user_id, reason, db, note=note)


def mark_due_no_shows(
    db: Session,
    now: Optional[datetime] = None,
    commit: bool = True,
) -> int:
    """Mark expired reserved bookings and charge each booking once.

    The row lock plus deterministic event id keeps repeated API calls safe.
    The application calls this opportunistically; a scheduler can call the
    admin reconcile endpoint if no traffic occurs after a slot ends.
    """
    now_naive = _as_naive(now or datetime.now())
    candidates = db.query(models.Booking).filter(
        models.Booking.status == "reserved",
        models.Booking.booking_date <= now_naive.date(),
    ).with_for_update().all()

    changed_count = 0
    for booking in candidates:
        if not booking.end_time:
            continue
        due_at = datetime.combine(booking.booking_date, booking.end_time) + NO_SHOW_GRACE
        if due_at > now_naive:
            continue

        booking.status = "no_show"
        booking.no_show_at = now_naive
        apply_point_event(
            booking.user_id,
            "no_show",
            db,
            note=f"ไม่เข้าร่วมการจองห้อง #{booking.id}",
            event_id=f"booking:{booking.id}:no_show",
            source_type="booking",
            source_id=booking.id,
            effective_at=now_naive,
            commit=False,
        )
        changed_count += 1

    if commit:
        db.commit()
    return changed_count


def get_booking_restriction(user_id: int, db: Session) -> dict:
    record = get_or_create_points(user_id, db)
    points = _clamp_score(record.points)
    if record.points != points:
        record.points = points
    ban_until = is_user_banned(user_id, db)
    reasons = []
    if points < BOOKING_MIN_POINTS:
        reasons.append(f"คะแนน {points} ต่ำกว่าเกณฑ์ {BOOKING_MIN_POINTS}")
    if ban_until:
        reasons.append("บัญชีถูกระงับการจองชั่วคราว")

    return {
        "points": points,
        "booking_min_points": BOOKING_MIN_POINTS,
        "booking_allowed": not reasons,
        "booking_block_reason": " และ ".join(reasons) if reasons else None,
        "is_banned": ban_until is not None,
        "ban_until": ban_until,
        "warning_level": "critical" if points < 40 else "warning" if points < BOOKING_MIN_POINTS else "normal",
    }


def _get_daily_score(user_id: int, score_date: date, db: Session) -> int:
    record = db.query(models.UserDailyScore).filter(
        models.UserDailyScore.user_id == user_id,
        models.UserDailyScore.score_date == score_date,
    ).first()
    return _clamp_score(record.score) if record else MAX_POINTS


def _points_response(user_id: int, db: Session) -> dict:
    restriction = get_booking_restriction(user_id, db)
    today = _now_utc().date()
    return {
        "user_id": user_id,
        **restriction,
        "daily_score": _get_daily_score(user_id, today, db),
        "daily_score_date": today,
    }


def _get_user_or_404(user_id: int, db: Session) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


def _logs_response(user_id: int, db: Session, limit: int, before_id: Optional[int]) -> dict:
    query = db.query(models.PointLog).filter(models.PointLog.user_id == user_id)
    if before_id is not None:
        query = query.filter(models.PointLog.id < before_id)

    logs = query.order_by(
        models.PointLog.id.desc(),
    ).limit(limit + 1).all()
    has_more = len(logs) > limit
    logs = logs[:limit]
    next_cursor = str(logs[-1].id) if has_more and logs else None

    return {
        "data": [
            {
                "id": log.id,
                "change": log.change,
                "reason": log.reason,
                "note": log.note,
                "points_before": log.points_before,
                "points_after": log.points_after,
                "daily_score_before": log.daily_score_before,
                "daily_score_after": log.daily_score_after,
                "score_date": log.score_date,
                "source_type": log.source_type,
                "source_id": log.source_id,
                "created_at": log.created_at,
            }
            for log in logs
        ],
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


@router.get("/users/me/points")
def get_my_points(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mark_due_no_shows(db)
    result = _points_response(current_user.id, db)
    db.commit()  # persist a legacy user's initial account if one was created
    return result


@router.get("/users/{user_id}/points")
def get_user_points(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    _require_user_access(user_id, current_user, db)
    mark_due_no_shows(db)
    result = _points_response(user_id, db)
    db.commit()
    return result


@router.get("/users/me/points/logs")
def get_my_point_logs(
    limit: int = Query(30, ge=1, le=100),
    before_id: Optional[int] = Query(None, gt=0),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mark_due_no_shows(db)
    return _logs_response(current_user.id, db, limit, before_id)


@router.get("/users/{user_id}/points/logs")
def get_point_logs(
    user_id: int,
    limit: int = Query(30, ge=1, le=100),
    before_id: Optional[int] = Query(None, gt=0),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    _require_user_access(user_id, current_user, db)
    mark_due_no_shows(db)
    return _logs_response(user_id, db, limit, before_id)


@router.get("/users/me/points/daily")
def get_my_daily_scores(
    limit: int = Query(30, ge=1, le=100),
    before_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mark_due_no_shows(db)
    query = db.query(models.UserDailyScore).filter(
        models.UserDailyScore.user_id == current_user.id,
    )
    if before_date:
        query = query.filter(models.UserDailyScore.score_date < before_date)
    rows = query.order_by(models.UserDailyScore.score_date.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "data": [
            {"score_date": row.score_date, "score": _clamp_score(row.score)}
            for row in rows
        ],
        "has_more": has_more,
        "next_cursor": rows[-1].score_date if has_more and rows else None,
    }


@router.post("/admin/points/reconcile-no-shows")
def reconcile_no_shows(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_admin_user(current_user.id, db):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return {"processed": mark_due_no_shows(db)}


@router.get("/admin/points/low")
def get_low_point_users(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_admin_user(current_user.id, db):
        raise HTTPException(status_code=403, detail="Admin access required.")

    mark_due_no_shows(db)
    rows = db.query(models.UserPoints, models.User).join(
        models.User,
        models.User.id == models.UserPoints.user_id,
    ).filter(
        models.UserPoints.points < BOOKING_MIN_POINTS,
    ).order_by(models.UserPoints.points.asc()).all()

    result = []
    for points, user in rows:
        ban_until = is_user_banned(points.user_id, db)
        result.append({
            "user_id": points.user_id,
            "email": user.email,
            "name": f"{user.first_name} {user.last_name}",
            "points": points.points,
            "is_banned": ban_until is not None,
            "ban_until": ban_until,
        })
    return {"data": result}
