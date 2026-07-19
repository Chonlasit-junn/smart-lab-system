from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
import os
import models
from database import get_db

router = APIRouter(tags=["Users"])

SECRET_KEY = os.getenv("SECRET_KEY", "SmartLab_Super_Secret_Key_2026")
ALGORITHM  = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user

router = APIRouter(tags=["Users"])

@router.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    return {"data": db.query(models.User).all()}

@router.get("/users/me")
def get_my_profile(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    role_row = db.query(models.Role.name).join(models.UserRole).filter(
        models.UserRole.user_id == current_user.id
    ).first()
    role = role_row[0] if role_row else "guest"

    extra = {}
    if role == "student":
        student = db.query(models.Student).filter(models.Student.user_id == current_user.id).first()
        if student:
            extra = {"student_id": student.student_id, "faculty": student.faculty, "department": student.department}
    elif role == "guest":
        passport = db.query(models.UserPassport).filter(models.UserPassport.user_id == current_user.id).first()
        if passport:
            extra = {"phone": passport.phone, "is_active": passport.is_active}

    total_bookings = db.query(models.Booking).filter(models.Booking.user_id == current_user.id).count()

    return {
        "id": current_user.id,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "email": current_user.email,
        "profile_pic": current_user.profile_pic,
        "role": role,
        "created_at": current_user.created_at,
        "stats": {"total_bookings": total_bookings},
        **extra,
    }