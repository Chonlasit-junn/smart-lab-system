"""Admin provisioning and lifecycle APIs for Lab workstations."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from database import get_db
from device_registry import (
    clean_device_id,
    clean_device_mac,
    clean_device_name,
    hash_device_token,
)
from routers.users import require_admin_user


router = APIRouter(tags=["Lab Devices"])
VALID_DEVICE_STATUSES = {"active", "maintenance", "revoked"}


class EnrollmentCodeCreate(BaseModel):
    lab_id: int
    expires_in_minutes: int = Field(10, ge=5, le=60)


class AdminDeviceRegister(BaseModel):
    lab_id: int
    device_id: str = Field(..., min_length=1, max_length=128)
    device_name: str = Field(..., min_length=1, max_length=255)
    device_mac: Optional[str] = Field(None, max_length=64)
    agent_version: Optional[str] = Field(None, max_length=64)


class LabDeviceUpdate(BaseModel):
    status: Optional[str] = None
    lab_id: Optional[int] = None
    device_name: Optional[str] = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_enrollment_code(value: str) -> str:
    return "".join(str(value or "").split()).upper()


def _serialize_device(device: models.LabDevice, lab: models.Lab) -> dict:
    return {
        "id": device.id,
        "device_id": device.device_id,
        "device_name": device.device_name,
        "device_mac": device.device_mac,
        "status": device.status,
        "agent_version": device.agent_version,
        "last_seen_at": device.last_seen_at,
        "created_at": device.created_at,
        "updated_at": device.updated_at,
        "lab": {
            "id": lab.id,
            "code": lab.code,
            "name": lab.name,
            "status": lab.status,
        },
    }


def _provision_device(
    db: Session,
    lab: models.Lab,
    device_id: str,
    device_name: str,
    device_mac: Optional[str],
    agent_version: Optional[str],
    now: datetime,
) -> tuple[models.LabDevice, str]:
    existing = db.query(models.LabDevice).filter(
        models.LabDevice.device_id == device_id,
    ).with_for_update().first()
    if existing and existing.status != "revoked" and existing.lab_id != lab.id:
        raise HTTPException(
            status_code=409,
            detail="This device is already assigned to another Lab.",
        )

    raw_device_token = secrets.token_urlsafe(32)
    resolved_mac = clean_device_mac(device_mac)
    resolved_version = (agent_version or "").strip()[:64] or None
    if existing:
        existing.lab_id = lab.id
        existing.device_name = device_name
        existing.device_mac = resolved_mac
        existing.status = "active"
        existing.agent_token_hash = hash_device_token(raw_device_token)
        existing.agent_version = resolved_version
        existing.last_seen_at = now
        device = existing
    else:
        device = models.LabDevice(
            device_id=device_id,
            lab_id=lab.id,
            device_name=device_name,
            device_mac=resolved_mac,
            status="active",
            agent_token_hash=hash_device_token(raw_device_token),
            agent_version=resolved_version,
            last_seen_at=now,
        )
        db.add(device)
        db.flush()

    return device, raw_device_token


@router.post("/admin/lab-devices/enrollment-codes")
def create_enrollment_code(
    payload: EnrollmentCodeCreate,
    admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    lab = db.query(models.Lab).filter(models.Lab.id == payload.lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found.")
    if lab.status != "active":
        raise HTTPException(status_code=409, detail="Only an active Lab can enroll devices.")

    raw_code = secrets.token_hex(12).upper()
    expires_at = _utc_now() + timedelta(minutes=payload.expires_in_minutes)
    enrollment = models.LabDeviceEnrollment(
        lab_id=lab.id,
        token_hash=hash_device_token(raw_code),
        expires_at=expires_at,
        created_by=admin.id,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return {
        "enrollment_code": raw_code,
        "expires_at": expires_at,
        "expires_in_minutes": payload.expires_in_minutes,
        "lab": {"id": lab.id, "code": lab.code, "name": lab.name},
    }


@router.post("/admin/lab-devices/register", status_code=201)
def register_device_as_admin(
    payload: AdminDeviceRegister,
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    resolved_device_id = clean_device_id(payload.device_id)
    resolved_device_name = clean_device_name(payload.device_name)
    if not resolved_device_id or not resolved_device_name:
        raise HTTPException(status_code=422, detail="device_id and device_name are required.")

    lab = db.query(models.Lab).filter(models.Lab.id == payload.lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found.")
    if lab.status != "active":
        raise HTTPException(status_code=409, detail="Only an active Lab can enroll devices.")

    device, raw_device_token = _provision_device(
        db,
        lab,
        resolved_device_id,
        resolved_device_name,
        payload.device_mac,
        payload.agent_version,
        _utc_now(),
    )
    db.commit()
    db.refresh(device)
    return {
        "message": "Device registered successfully.",
        "device_id": device.device_id,
        "device_token": raw_device_token,
        "device": _serialize_device(device, lab),
    }


@router.get("/admin/lab-devices")
def list_lab_devices(
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    rows = db.query(models.LabDevice, models.Lab).join(
        models.Lab,
        models.Lab.id == models.LabDevice.lab_id,
    ).order_by(models.Lab.code.asc(), models.LabDevice.device_name.asc()).all()
    return {"data": [_serialize_device(device, lab) for device, lab in rows]}


@router.put("/admin/lab-devices/{device_pk}")
def update_lab_device(
    device_pk: int,
    payload: LabDeviceUpdate,
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    device = db.query(models.LabDevice).filter(models.LabDevice.id == device_pk).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")

    if payload.status is not None:
        new_status = payload.status.strip().lower()
        if new_status not in VALID_DEVICE_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid device status.")
        device.status = new_status
        if new_status == "revoked":
            # Keep the column non-null while making the old credential unusable.
            device.agent_token_hash = hash_device_token(secrets.token_urlsafe(32))

    if payload.lab_id is not None and payload.lab_id != device.lab_id:
        active_session = db.query(models.LabAccessLog).filter(
            models.LabAccessLog.lab_device_id == device.id,
            models.LabAccessLog.session_status == "active",
            models.LabAccessLog.exit_time.is_(None),
        ).first()
        if active_session:
            raise HTTPException(
                status_code=409,
                detail="Cannot move a device while it has an active session.",
            )
        target_lab = db.query(models.Lab).filter(models.Lab.id == payload.lab_id).first()
        if not target_lab:
            raise HTTPException(status_code=404, detail="Target Lab not found.")
        if target_lab.status != "active":
            raise HTTPException(status_code=409, detail="Target Lab is not active.")
        device.lab_id = target_lab.id

    if payload.device_name is not None:
        device.device_name = clean_device_name(payload.device_name) or device.device_name

    db.commit()
    db.refresh(device)
    lab = db.query(models.Lab).filter(models.Lab.id == device.lab_id).first()
    return {"message": "Device updated successfully.", "device": _serialize_device(device, lab)}


@router.post("/agent/register-device")
def register_device(
    enrollment_code: str = Form(...),
    device_id: str = Form(...),
    device_name: str = Form(...),
    device_mac: Optional[str] = Form(None),
    agent_version: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    normalized_code = _normalise_enrollment_code(enrollment_code)
    resolved_device_id = clean_device_id(device_id)
    resolved_device_name = clean_device_name(device_name)
    if not normalized_code or not resolved_device_id or not resolved_device_name:
        raise HTTPException(
            status_code=422,
            detail="enrollment_code, device_id and device_name are required.",
        )

    enrollment = db.query(models.LabDeviceEnrollment).filter(
        models.LabDeviceEnrollment.token_hash == hash_device_token(normalized_code),
    ).with_for_update().first()
    if not enrollment:
        raise HTTPException(status_code=403, detail="Invalid enrollment code.")
    if enrollment.used_at is not None:
        raise HTTPException(status_code=409, detail="Enrollment code has already been used.")

    now = _utc_now()
    expires_at = enrollment.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(status_code=410, detail="Enrollment code has expired.")

    lab = db.query(models.Lab).filter(models.Lab.id == enrollment.lab_id).first()
    if not lab or lab.status != "active":
        raise HTTPException(status_code=409, detail="The assigned Lab is not active.")

    device, raw_device_token = _provision_device(
        db,
        lab,
        resolved_device_id,
        resolved_device_name,
        device_mac,
        agent_version,
        now,
    )

    enrollment.used_at = now
    enrollment.used_device_id = resolved_device_id
    db.commit()
    db.refresh(device)
    return {
        "message": "Device registered successfully.",
        "device_id": device.device_id,
        "device_token": raw_device_token,
        "device": _serialize_device(device, lab),
    }
