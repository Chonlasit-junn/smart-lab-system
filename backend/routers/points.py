from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import models
from database import get_db

router = APIRouter(tags=["Point System"])

# ── กฎการหักคะแนน ─────────────────────────────────────────────────────────────
POINT_RULES = {
    "no_show":          -5,   # จองแล้วไม่มา
    "forbidden_app":   -10,   # เปิดโปรแกรมต้องห้ามในแล็บ
    "late_cancel":      -3,   # ยกเลิกก่อนเวลา < 1 ชม.
    "complete_session": +1,   # จบ session ปกติ
}

# ── กฎ Ban ─────────────────────────────────────────────────────────────────────
BAN_RULES = [
    {"below": 80, "ban_days": 1},
    {"below": 60, "ban_days": 3},
    {"below": 40, "ban_days": 7},
    {"below": 20, "ban_days": 30},
]


# ── Helper functions ───────────────────────────────────────────────────────────

def get_or_create_points(user_id: int, db: Session) -> models.UserPoints:
    """ดึง UserPoints record — ถ้ายังไม่มีสร้างใหม่ด้วยคะแนน 100"""
    record = db.query(models.UserPoints).filter(models.UserPoints.user_id == user_id).first()
    if not record:
        record = models.UserPoints(user_id=user_id, points=100)
        db.add(record)
        db.flush()
    return record


def apply_ban_if_needed(user_id: int, points: int, db: Session) -> Optional[int]:
    """
    เช็คว่าคะแนนต่ำพอที่จะ ban ไหม
    ถ้าใช่ สร้าง BanRecord และคืนจำนวนวันที่ ban
    """
    ban_days = None
    for rule in sorted(BAN_RULES, key=lambda r: r["below"]):
        if points < rule["below"]:
            ban_days = rule["ban_days"]

    if ban_days:
        ban_until = datetime.now() + timedelta(days=ban_days)
        db.add(models.BanRecord(
            user_id=user_id,
            ban_until=ban_until,
            reason=f"คะแนนต่ำกว่าเกณฑ์ ({points} คะแนน)",
        ))
    return ban_days


def deduct_points(user_id: int, reason: str, db: Session, note: str = None) -> dict:
    """
    หักหรือเพิ่มคะแนน user ตาม reason
    คืน dict บอกคะแนนก่อน/หลัง และสถานะ ban
    """
    change = POINT_RULES.get(reason)
    if change is None:
        raise ValueError(f"Unknown reason: {reason}")

    record = get_or_create_points(user_id, db)
    before = record.points
    record.points = max(0, record.points + change)  # ไม่ให้ติดลบ
    after  = record.points

    # บันทึก log
    db.add(models.PointLog(
        user_id=user_id,
        change=change,
        reason=reason,
        note=note,
    ))

    # เช็คว่าต้อง ban ไหม
    ban_days = apply_ban_if_needed(user_id, after, db)
    db.commit()

    return {"before": before, "after": after, "change": change, "ban_days": ban_days}


def is_user_banned(user_id: int, db: Session) -> Optional[datetime]:
    """
    เช็คว่า user ถูก ban อยู่ไหม
    คืน ban_until ถ้าถูก ban, None ถ้าไม่ถูก ban
    """
    active_ban = db.query(models.BanRecord).filter(
        models.BanRecord.user_id == user_id,
        models.BanRecord.ban_until > datetime.now(),
    ).order_by(models.BanRecord.ban_until.desc()).first()

    return active_ban.ban_until if active_ban else None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/points")
def get_user_points(user_id: int, db: Session = Depends(get_db)):
    """ดูคะแนนและสถานะ ban ของ user"""
    record   = get_or_create_points(user_id, db)
    ban_until = is_user_banned(user_id, db)

    return {
        "user_id":   user_id,
        "points":    record.points,
        "is_banned": ban_until is not None,
        "ban_until": ban_until,
    }


@router.get("/users/{user_id}/points/logs")
def get_point_logs(user_id: int, db: Session = Depends(get_db)):
    """ดูประวัติการเปลี่ยนแปลงคะแนนของ user"""
    logs = db.query(models.PointLog).filter(
        models.PointLog.user_id == user_id
    ).order_by(models.PointLog.created_at.desc()).all()

    return {"data": logs}


@router.get("/admin/points/low")
def get_low_point_users(db: Session = Depends(get_db)):
    """Admin — ดู user ที่คะแนนต่ำกว่า 80"""
    records = db.query(models.UserPoints).filter(
        models.UserPoints.points < 80
    ).order_by(models.UserPoints.points.asc()).all()

    result = []
    for r in records:
        user      = db.query(models.User).filter(models.User.id == r.user_id).first()
        ban_until = is_user_banned(r.user_id, db)
        if user:
            result.append({
                "user_id":   r.user_id,
                "email":     user.email,
                "name":      f"{user.first_name} {user.last_name}",
                "points":    r.points,
                "is_banned": ban_until is not None,
                "ban_until": ban_until,
            })

    return {"data": result}