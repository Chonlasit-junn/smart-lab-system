"""Bounded cleanup for records with an explicit expiration timestamp."""

from datetime import timedelta

from sqlalchemy.orm import Session

import models
from otp_service import IP_RATE_LIMIT_WINDOW_SECONDS
from time_utils import utc_now

MAX_CLEANUP_BATCH_SIZE = 500


def _delete_expired_batch(
    db: Session, model, expiry_column, cutoff, batch_size, extra_condition=None,
):
    query = db.query(model).filter(expiry_column <= cutoff)
    if extra_condition is not None:
        query = query.filter(extra_condition)
    rows = query.order_by(expiry_column.asc()).limit(batch_size).with_for_update(skip_locked=True).all()
    count = len(rows)
    for row in rows:
        db.delete(row)
    db.commit()
    remaining = db.query(model).filter(expiry_column <= cutoff)
    if extra_condition is not None:
        remaining = remaining.filter(extra_condition)
    has_more = remaining.first() is not None
    return {"deleted": count, "has_more": has_more}


def cleanup_expired_data(db: Session, *, batch_size=100):
    """Delete at most ``batch_size`` rows per explicitly expiring table.

    Used device enrollments and legacy plaintext UserOTP rows are deliberately
    retained; neither has a safe expiry contract for this cleanup operation.
    """
    if not isinstance(batch_size, int) or not 1 <= batch_size <= MAX_CLEANUP_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_CLEANUP_BATCH_SIZE}")
    now = utc_now()
    results = {
        "registration_otps": _delete_expired_batch(
            db, models.RegistrationOTP, models.RegistrationOTP.expires_at, now, batch_size,
        ),
        "password_reset_otps": _delete_expired_batch(
            db, models.PasswordResetOTP, models.PasswordResetOTP.expires_at, now, batch_size,
        ),
        "otp_ip_rate_limits": _delete_expired_batch(
            db, models.OTPIPRateLimit, models.OTPIPRateLimit.window_started_at,
            now - timedelta(seconds=IP_RATE_LIMIT_WINDOW_SECONDS), batch_size,
        ),
        "unused_device_enrollments": _delete_expired_batch(
            db, models.LabDeviceEnrollment,
            models.LabDeviceEnrollment.expires_at, now, batch_size,
            models.LabDeviceEnrollment.used_at.is_(None),
        ),
    }
    return {
        "batch_size_per_table": batch_size,
        "deleted": {name: result["deleted"] for name, result in results.items()},
        "has_more": {name: result["has_more"] for name, result in results.items()},
    }
