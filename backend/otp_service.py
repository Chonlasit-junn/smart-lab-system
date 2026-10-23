"""Shared issuance/verification boundary for purpose-isolated email OTPs.

No application imports with startup DDL. Email is the serialization key, with
PostgreSQL upsert + row locks for first issuance, retries and consumption.
"""

import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import secrets
from datetime import timedelta, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from database import get_db
from models import OTPIPRateLimit, PasswordResetOTP, RegistrationOTP
from time_utils import as_utc, utc_now


TTL_SECONDS = 600
RESEND_SECONDS = 60
MAX_ATTEMPTS = 5
ATTEMPT_WINDOW_SECONDS = 600
IP_RATE_LIMIT_WINDOW_SECONDS = 600
IP_RATE_LIMIT_MAX_REQUESTS = 30

INVALID = "Invalid OTP. Please try again."
EXPIRED = "OTP expired. Please request a new code."
REPLACED = "OTP replaced. Please use the latest code."
EXHAUSTED = "Too many OTP attempts. Please wait and request a new code."
COOLDOWN = "Please wait before requesting another OTP."
UNAVAILABLE = "OTP delivery is unavailable. Please try again later."
NOT_CONFIGURED = "OTP service is not configured. Please contact support."


def _instant(value):
    # SQLite tests drop tzinfo; OTP timestamps always represent UTC.
    return as_utc(value, naive_timezone=timezone.utc)


def _key():
    key = os.getenv("OTP_SECRET_KEY") or os.getenv("SECRET_KEY", "")
    if len(key.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED)
    return key.encode("utf-8")


def enforce_ip_rate_limit(request: Request, db: Session = Depends(get_db)):
    """Apply one shared OTP request budget per trusted client IP.

    The raw IP is never stored. ``request.client`` must reflect the actual
    client, either directly or through the ASGI server's trusted-proxy setup.
    """
    client_ip = request.client.host if request.client else "unknown"
    try:
        client_ip = ipaddress.ip_address(client_ip).compressed
    except ValueError:
        client_ip = str(client_ip).strip().lower() or "unknown"
    ip_hash = hmac.new(
        _key(), b"otp-ip-rate-limit:v1:" + client_ip.encode("utf-8"), hashlib.sha256,
    ).hexdigest()

    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    db.execute(insert(OTPIPRateLimit).values(
        ip_hash=ip_hash,
        window_started_at=utc_now(),
        request_count=0,
    ).on_conflict_do_nothing(index_elements=[OTPIPRateLimit.ip_hash]))
    row = db.query(OTPIPRateLimit).filter(
        OTPIPRateLimit.ip_hash == ip_hash,
    ).populate_existing().with_for_update().first()
    now = utc_now()
    window_started = _instant(row.window_started_at)
    if now >= window_started + timedelta(seconds=IP_RATE_LIMIT_WINDOW_SECONDS):
        row.window_started_at = now
        row.request_count = 0
        window_started = now
    if row.request_count >= IP_RATE_LIMIT_MAX_REQUESTS:
        retry_after = math.ceil((
            window_started + timedelta(seconds=IP_RATE_LIMIT_WINDOW_SECONDS) - now
        ).total_seconds())
        _reject(
            db,
            "Too many OTP requests. Please try again later.",
            status=429,
            retry_after=retry_after,
        )
    row.request_count += 1
    db.commit()


def _digest(email, challenge_id, code, *, purpose="registration"):
    message = json.dumps(
        [f"{purpose}-otp:v1", email, challenge_id, code],
        separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hmac.new(_key(), message, hashlib.sha256).hexdigest()


def _reject(db, message, *, status=400, retry_after=None, persist=False):
    # Wrong guesses must survive the HTTP error. Never commit partial account
    # creation: the caller checks/consumes before adding a User to the session.
    if persist:
        db.commit()
    else:
        db.rollback()
    headers = {"Retry-After": str(max(1, retry_after))} if retry_after is not None else None
    raise HTTPException(status_code=status, detail=message, headers=headers)


def _locked(db, email, *, create=False, purpose="registration"):
    model = {"registration": RegistrationOTP, "password-reset": PasswordResetOTP}[purpose]
    if create:
        dialect = db.get_bind().dialect.name
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        db.execute(insert(model).values(email=email).on_conflict_do_nothing(
            index_elements=[model.email],
        ))
    return db.query(model).filter(
        model.email == email,
    ).populate_existing().with_for_update().first()


def _reset_window(row, now):
    start = _instant(row.attempt_window_started_at)
    if start is None or now >= start + timedelta(seconds=ATTEMPT_WINDOW_SECONDS):
        row.attempt_window_started_at = now
        row.window_attempts = 0


def _window_wait(row, now):
    return max(1, math.ceil((
        _instant(row.attempt_window_started_at)
        + timedelta(seconds=ATTEMPT_WINDOW_SECONDS) - now
    ).total_seconds()))


def reserve_otp(db, email, *, purpose="registration", binding=None):
    """Reserve before sending; a pending/failed email can never authorize a user."""
    _key()  # Fail before changing even test/local challenge state.
    row = _locked(db, email, create=True, purpose=purpose)
    now = utc_now()
    _reset_window(row, now)
    if row.window_attempts >= MAX_ATTEMPTS:
        _reject(db, EXHAUSTED, status=429, retry_after=_window_wait(row, now))
    if row.last_sent_at is not None:
        wait = RESEND_SECONDS - (now - _instant(row.last_sent_at)).total_seconds()
        if wait > 0:
            _reject(db, COOLDOWN, status=429, retry_after=math.ceil(wait))

    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge_id = uuid4().hex
    row.challenge_id = challenge_id
    row.code_hash = _digest(email, challenge_id, code, purpose=purpose)
    if purpose == "password-reset":
        row.user_id, row.credential_hash = binding or (None, None)
    row.expires_at = now + timedelta(seconds=TTL_SECONDS)
    row.last_sent_at = now
    row.delivered_at = None
    row.consumed_at = None
    row.failed_attempts = 0
    # window_attempts deliberately survives resends.
    db.commit()  # Release the lock before awaiting the external mail provider.
    return challenge_id, code


def finish_delivery(db, email, challenge_id, *, success, purpose="registration"):
    """A late mail response must not activate/invalidate a newer challenge."""
    row = _locked(db, email, purpose=purpose)
    if row is None or row.challenge_id != challenge_id:
        _reject(db, REPLACED)
    now = utc_now()
    if not success:
        row.code_hash = None
        row.delivered_at = None
        db.commit()  # Keep cooldown and guessing budget even when mail fails.
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    row.delivered_at = now
    expires_at = _instant(row.expires_at)
    resend_at = _instant(row.last_sent_at) + timedelta(seconds=RESEND_SECONDS)
    db.commit()
    return {
        "expires_at": expires_at,
        "expires_in_seconds": max(0, math.ceil((expires_at - now).total_seconds())),
        "retry_after_seconds": max(0, math.ceil((resend_at - now).total_seconds())),
    }


def verify_otp(db, email, code, *, consume=False, expected_challenge_id=None, purpose="registration"):
    """Verify without consumption; consume only in the account's transaction.

    Call before creating any account rows. Normal verification commits to release
    its lock before face processing. Final consumption stays uncommitted so a
    failed registration can roll it back together with the account.
    """
    row = _locked(db, email, purpose=purpose)
    now = utc_now()
    if row is None:
        _reject(db, EXPIRED)
    if expected_challenge_id is not None and row.challenge_id != expected_challenge_id:
        _reject(db, REPLACED)
    if row.consumed_at is not None or row.delivered_at is None or not row.code_hash:
        _reject(db, EXPIRED)
    if row.expires_at is None or now >= _instant(row.expires_at):
        _reject(db, EXPIRED)
    _reset_window(row, now)
    if row.failed_attempts >= MAX_ATTEMPTS or row.window_attempts >= MAX_ATTEMPTS:
        _reject(db, EXHAUSTED, status=429, retry_after=_window_wait(row, now))
    matches = bool(re.fullmatch(r"[0-9]{6}", code)) and hmac.compare_digest(
        row.code_hash, _digest(email, row.challenge_id, code, purpose=purpose),
    )
    if not matches:
        if consume:
            # Preflight already checked this request. Never commit pending
            # account rows if the key/state changed during face processing.
            _reject(db, REPLACED)
        row.failed_attempts += 1
        row.window_attempts += 1
        exhausted = row.failed_attempts >= MAX_ATTEMPTS or row.window_attempts >= MAX_ATTEMPTS
        _reject(
            db, EXHAUSTED if exhausted else INVALID,
            status=429 if exhausted else 400,
            retry_after=_window_wait(row, now) if exhausted else None,
            persist=True,
        )
    challenge_id = row.challenge_id
    if consume:
        row.consumed_at = now
    else:
        db.commit()
    return challenge_id
