"""Admin-only, read-only report downloads. Never call point/booking mutations."""

from datetime import date
from threading import BoundedSemaphore
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

import models
from database import get_db
from routers.users import require_admin_user
from usage_report import ReportFilters, build_usage_workbook


router = APIRouter(prefix="/admin/reports", tags=["Admin Reports"])
_export_slots = BoundedSemaphore(2)


@router.get("/options")
def report_options(_admin: models.User = Depends(require_admin_user), db: Session = Depends(get_db)):
    with db.no_autoflush:
        labs = db.query(models.Lab.id, models.Lab.code, models.Lab.name).order_by(models.Lab.code).all()
        devices = db.query(models.LabDevice.id, models.LabDevice.device_id, models.LabDevice.device_name).order_by(models.LabDevice.device_name, models.LabDevice.id).all()
    return {"labs": [dict(row._mapping) for row in labs], "devices": [dict(row._mapping) for row in devices]}


@router.get("/users")
def report_users(
    q: str = Query("", max_length=100),
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    term = q.strip().lower()
    if len(term) < 2:
        return {"data": [], "has_more": False}
    with db.no_autoflush:
        # contains(autoescape=True) treats user-supplied % and _ literally.
        rows = db.query(models.User.id, models.User.first_name, models.User.last_name, models.User.email).filter(or_(
            func.lower(models.User.email).contains(term, autoescape=True),
            func.lower(models.User.first_name + " " + models.User.last_name).contains(term, autoescape=True),
        )).order_by(models.User.id).limit(21).all()
    return {"data": [dict(row._mapping) for row in rows[:20]], "has_more": len(rows) > 20}


def _file_chunks(handle):
    try:
        while chunk := handle.read(64 * 1024):
            yield chunk
    finally:
        handle.close()


@router.get("/usage.xlsx")
def export_usage(
    date_from: date,
    date_to: date,
    lab_id: Optional[int] = Query(None, ge=1),
    device_id: Optional[int] = Query(None, ge=1),
    user_id: Optional[int] = Query(None, ge=1),
    language: Literal["th", "en"] = "th",
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    filters = ReportFilters(date_from, date_to, lab_id, device_id, user_id, language)
    if not _export_slots.acquire(blocking=False):
        raise HTTPException(429, detail="REPORT_BUSY", headers={"Retry-After": "10"})
    try:
        handle = build_usage_workbook(db, filters)
    finally:
        _export_slots.release()
    filename = f"smart-lab-usage_{date_from.isoformat()}_{date_to.isoformat()}_{language}.xlsx"
    return StreamingResponse(_file_chunks(handle), background=BackgroundTask(handle.close), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })
