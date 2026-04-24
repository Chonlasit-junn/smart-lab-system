import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session

import models
from database import get_db

router = APIRouter(tags=["Hardware Agent"])

@router.post("/agent/start-session")
def start_session(email: str = Form(...), lab_code: str = Form(...), device: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    lab = db.query(models.Lab).filter(models.Lab.code == lab_code).first()
    
    if not user or not lab:
        raise HTTPException(status_code=404, detail="Invalid credentials.")

    new_log = models.LabAccessLog(
        lab_id=lab.id, user_id=user.id, access_type="manual", status="success", device_used=device
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return {"session_id": new_log.id}

@router.post("/agent/log-usage")
def log_usage(session_id: int = Form(...), usage_data: str = Form(...), db: Session = Depends(get_db)):
    try:
        logs = json.loads(usage_data)
        for item in logs:
            db.add(models.ProgramUsageLog(
                lab_access_log_id=session_id, program_name=item['name'],
                duration_seconds=item['duration'], usage_start_time=datetime.utcnow(), usage_end_time=datetime.utcnow()
            ))
        
        access_log = db.query(models.LabAccessLog).filter(models.LabAccessLog.id == session_id).first()
        if access_log:
            access_log.exit_time = datetime.utcnow()
            
        db.commit()
        return {"message": "Data logged successfully."}
    except Exception as e:
        db.rollback() 
        raise HTTPException(status_code=500, detail=str(e))