"""Shared helpers for provisioning and authenticating Lab workstations."""

from __future__ import annotations

import hashlib
import hmac
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


def require_registered_device(
    db: Session,
    device_id: Optional[str],
    device_token: Optional[str],
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
    if device.status != "active":
        raise HTTPException(
            status_code=403,
            detail="This workstation is not available for Lab sessions.",
        )

    expected_hash = device.agent_token_hash or ""
    if not hmac.compare_digest(hash_device_token(resolved_token), expected_hash):
        raise HTTPException(status_code=403, detail="Invalid workstation credential.")

    return device
