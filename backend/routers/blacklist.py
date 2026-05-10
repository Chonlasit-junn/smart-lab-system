from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
import models
from database import get_db

router = APIRouter(prefix="/admin/blacklist", tags=["Blacklist"])


class BlacklistCreate(BaseModel):
    app_name: str = Field(..., example="BitTorrent")
    description: Optional[str] = Field(None, example="ห้ามใช้โปรแกรมโหลดไฟล์ละเมิดลิขสิทธิ์")

class BlacklistUpdate(BaseModel):
    description: Optional[str] = None


@router.get("")
def get_all(db: Session = Depends(get_db)):
    apps = db.query(models.BlacklistedApp).order_by(models.BlacklistedApp.created_at.desc()).all()
    return {"data": apps}


@router.post("")
def create(payload: BlacklistCreate, db: Session = Depends(get_db)):
    exists = db.query(models.BlacklistedApp).filter(
        models.BlacklistedApp.app_name == payload.app_name
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail=f'"{payload.app_name}" is already blacklisted.')

    db.add(models.BlacklistedApp(app_name=payload.app_name, description=payload.description))
    db.commit()
    return {"message": f'"{payload.app_name}" added to blacklist.'}


@router.put("/{app_id}")
def update(app_id: int, payload: BlacklistUpdate, db: Session = Depends(get_db)):
    app = db.query(models.BlacklistedApp).filter(models.BlacklistedApp.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found.")

    app.description = payload.description
    db.commit()
    return {"message": "Description updated."}


@router.delete("/{app_id}")
def delete(app_id: int, db: Session = Depends(get_db)):
    app = db.query(models.BlacklistedApp).filter(models.BlacklistedApp.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found.")

    db.delete(app)
    db.commit()
    return {"message": f'"{app.app_name}" removed from blacklist.'}
