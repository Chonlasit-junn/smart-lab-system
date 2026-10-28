"""Shared, read-only account and Lab admission rules.

Authentication is separate from Lab admission: banned users can still read
their profile and contact support. No role bypasses a Lab booking or a ban.
"""

import models
from time_utils import utc_now


def role_names(db, user_id):
    return {name for (name,) in db.query(models.Role.name).join(
        models.UserRole, models.UserRole.role_id == models.Role.id,
    ).filter(models.UserRole.user_id == user_id).all()}


def primary_role(db, user_id):
    names = role_names(db, user_id)
    return next((role for role in ("admin", "student", "guest") if role in names), min(names, default="guest"))


def account_denial(db, user_id):
    names = role_names(db, user_id)
    passport = db.query(models.UserPassport).filter(models.UserPassport.user_id == user_id).first()
    if (
        (("guest" in names or not names) and (passport is None or not passport.is_active))
        or (passport is not None and not passport.is_active)
    ):
        return "guest_approval_required", "Your account is pending admin approval."
    student = db.query(models.Student).filter(models.Student.user_id == user_id).first()
    if student is not None and not student.is_active:
        return "account_inactive", "This account is not active."
    return None


def active_ban(db, user_id, *, now=None):
    return db.query(models.BanRecord).filter(
        models.BanRecord.user_id == user_id,
        models.BanRecord.ban_until > (now if now is not None else utc_now()),
    ).order_by(models.BanRecord.ban_until.desc()).first()


def lab_access_denial(db, user_id, *, now=None):
    denial = account_denial(db, user_id)
    if denial is not None:
        return denial
    if active_ban(db, user_id, now=now) is not None:
        return "user_banned", "This account has an active ban."
    return None


def current_lab_booking(db, user_id, lab_id, lab_time):
    """Bangkok wall clock: start inclusive, end exclusive, including reentry."""
    return db.query(models.Booking).filter(
        models.Booking.user_id == user_id,
        models.Booking.lab_id == lab_id,
        models.Booking.booking_date == lab_time.date(),
        models.Booking.start_time <= lab_time.time(),
        models.Booking.end_time > lab_time.time(),
        models.Booking.status.in_(("reserved", "attended")),
    ).order_by(models.Booking.start_time.asc(), models.Booking.id.asc()).first()
