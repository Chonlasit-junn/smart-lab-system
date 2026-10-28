"""Email recovery, isolated from registration and committed atomically."""

import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

import models
from access_policy import account_denial
import otp_service as otp
import schemas
from database import get_db
from utils import normalize_email, pwd_context, send_otp_mail

router = APIRouter(prefix="/password-reset", tags=["Password recovery"])
PURPOSE = "password-reset"
REQUEST_MESSAGE = "If an account exists, a password reset code will be sent to that email."


def _fingerprint(password):
    return hmac.new(otp._key(), b"password-reset-credential:v1:" + password.encode("utf-8"), hashlib.sha256).hexdigest()


def _reserve(db, email):
    user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
    eligible = _password_reset_eligible(db, user)
    binding = (user.id, _fingerprint(user.password)) if eligible else None
    challenge, code = otp.reserve_otp(db, email, purpose=PURPOSE, binding=binding)
    return challenge, code, eligible


def _password_reset_eligible(db, user):
    """Pending guests must not receive a password-reset OTP before approval."""
    if user is None:
        return False
    return account_denial(db, user.id) is None


@router.post("/request-otp", dependencies=[Depends(otp.enforce_ip_rate_limit)])
async def request_otp(request: schemas.OTPRequest, db: Session = Depends(get_db)):
    email = normalize_email(request.email)
    challenge, code, exists = await run_in_threadpool(_reserve, db, email)
    delivered = False
    if exists:
        try:
            await send_otp_mail(email, code, password_reset=True)
            delivered = True
        except Exception:
            # Never leak provider details or account existence in the response.
            pass
    try:
        await run_in_threadpool(
            otp.finish_delivery, db, email, challenge, success=delivered, purpose=PURPOSE,
        )
    except HTTPException as error:
        if error.detail not in {otp.UNAVAILABLE, otp.REPLACED}:
            raise
    return {"message": REQUEST_MESSAGE, "expires_in_seconds": otp.TTL_SECONDS,
            "retry_after_seconds": otp.RESEND_SECONDS}


def _verify(db, email, code):
    challenge = otp.verify_otp(db, email, code, purpose=PURPOSE)
    row = db.get(models.PasswordResetOTP, email, populate_existing=True)
    if row is None or row.challenge_id != challenge:
        otp._reject(db, otp.REPLACED)
    user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
    if (not _password_reset_eligible(db, user) or row.user_id != user.id or not row.credential_hash
            or not hmac.compare_digest(row.credential_hash, _fingerprint(user.password))):
        otp._reject(db, otp.EXPIRED)
    db.rollback()  # No locks/transaction held while hashing a new password.
    return challenge


@router.post("/verify-otp", dependencies=[Depends(otp.enforce_ip_rate_limit)])
def verify_otp(request: schemas.OTPVerify, db: Session = Depends(get_db)):
    _verify(db, normalize_email(request.email), request.otp)
    return {"message": "OTP Verified Successfully!"}


@router.post("/confirm", dependencies=[Depends(otp.enforce_ip_rate_limit)])
def confirm(request: schemas.PasswordReset, db: Session = Depends(get_db)):
    email = normalize_email(request.email)
    challenge = _verify(db, email, request.otp)
    hashed = pwd_context.hash(request.new_password)
    try:
        # Identical lock order for every final reset: OTP first, user second.
        otp.verify_otp(db, email, request.otp, consume=True,
                       expected_challenge_id=challenge, purpose=PURPOSE)
        row = db.get(models.PasswordResetOTP, email)
        user = db.query(models.User).filter(
            func.lower(models.User.email) == email,
        ).populate_existing().with_for_update().first()
        if (not user or user.id != row.user_id or not row.credential_hash
                or not hmac.compare_digest(row.credential_hash, _fingerprint(user.password))):
            otp._reject(db, otp.EXPIRED)
        user.password = hashed
        user.auth_version += 1
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=503, detail="Password reset is unavailable. Please try again.") from None
    return {"message": "Password reset successful. Please log in again."}
