"""Shared helpers for provisioning and authenticating Lab workstations."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models


def clean_device_id(value: Optional[str]) -> Optional[str]:
    cleaned = str(value or "").strip()
    return cleaned[:128] or None


def clean_device_name(value: Optional[str]) -> Optional[str]:
    cleaned = str(value or "").strip()
    return cleaned[:255] or None


def clean_device_mac(value: Optional[str]) -> Optional[str]:
    cleaned = str(value or "").strip().lower()
    return cleaned[:64] or None


def hash_device_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def resume_expired_maintenance(device: models.LabDevice, now: Optional[datetime] = None) -> bool:
    """Restore an Agent after its temporary maintenance lease expires."""
    if device.status != "maintenance" or device.maintenance_until is None:
        return False

    expires_at = device.maintenance_until
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if expires_at > now:
        return False

    device.status = "active"
    device.maintenance_until = None
    device.control_requested_at = now
    device.control_requested_by = None
    return True


def require_registered_device(
    db: Session,
    device_id: Optional[str],
    device_token: Optional[str],
    *,
    allow_maintenance: bool = False,
) -> models.LabDevice:
    """Resolve an active device from its public id and secret token."""

    resolved_device_id = clean_device_id(device_id)
    resolved_token = str(device_token or "").strip()
    if not resolved_device_id or not resolved_token:
        raise HTTPException(
            status_code=403,
            detail="This workstation must be registered before starting a session.",
        )

    device = db.query(models.LabDevice).filter(
        models.LabDevice.device_id == resolved_device_id,
    ).first()
    if not device:
        raise HTTPException(status_code=403, detail="This workstation is not registered.")
    expected_hash = device.agent_token_hash or ""
    if not hmac.compare_digest(hash_device_token(resolved_token), expected_hash):
        raise HTTPException(status_code=403, detail="Invalid workstation credential.")

    resume_expired_maintenance(device)
    if device.status != "active" and not (
        allow_maintenance and device.status == "maintenance"
    ):
        raise HTTPException(
            status_code=403,
            detail="This workstation is not available for Lab sessions.",
        )

    return device
