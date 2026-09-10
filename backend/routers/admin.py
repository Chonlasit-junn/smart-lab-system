from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import models
from database import get_db

router = APIRouter(prefix="/admin", tags=["Admin"])


class VerifyAction(BaseModel):
    action: str = Field(..., description="'approve' or 'reject'")


@router.get("/users/pending")
def get_pending_users(db: Session = Depends(get_db)):
    # join once instead of querying user individually in a loop (avoids N+1)
    pending = (
        db.query(models.User, models.UserPassport)
        .join(models.UserPassport, models.User.id == models.UserPassport.user_id)
        .filter(models.UserPassport.is_active == False)
        .all()
    )

    return {
        "data": [
            {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "profile_pic": user.profile_pic,
                "phone": passport.phone,
                "created_at": user.created_at,
            }
            for user, passport in pending
        ]
    }


@router.put("/users/{user_id}/verify")
def verify_user(user_id: int, payload: VerifyAction, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    passport = db.query(models.UserPassport).filter(models.UserPassport.user_id == user_id).first()

    if not user or not passport:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.action == "approve":
        passport.is_active = True
        db.commit()
        return {"message": "User approved successfully."}

    elif payload.action == "reject":
        # delete child records first, then flush so FK constraints are satisfied
        # before we delete the parent user row
        db.delete(passport)
        db.query(models.UserRole).filter(models.UserRole.user_id == user.id).delete()
        db.flush()
        db.delete(user)
        db.commit()
        return {"message": "User rejected and removed."}

    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'.")