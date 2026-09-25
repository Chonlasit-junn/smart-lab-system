from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import func
from jose import jwt, JWTError
import os
import models
from database import get_db
from profile_storage import get_profile_image_url
from utils import normalize_email

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
    user = db.query(models.User).filter(
        func.lower(models.User.email) == normalize_email(email),
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


def is_admin_user(user_id: int, db: Session) -> bool:
    return db.query(models.Role.id).join(
        models.UserRole,
        models.UserRole.role_id == models.Role.id,
    ).filter(
        models.UserRole.user_id == user_id,
        models.Role.name == "admin",
    ).first() is not None


def require_admin_user(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    if not is_admin_user(current_user.id, db):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


router = APIRouter(tags=["Users"])

@router.get("/users")
def get_all_users(
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    page_number = page if isinstance(page, int) else 1
    page_limit = page_size if isinstance(page_size, int) else 50
    query = db.query(models.User)
    total = query.order_by(None).count()
    users = query.order_by(models.User.id.asc()).offset(
        (page_number - 1) * page_limit
    ).limit(page_limit).all()
    return {
        "data": [
            {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "profile_pic": get_profile_image_url(user.profile_pic),
                "created_at": user.created_at,
            }
            for user in users
        ],
        "page": page_number,
        "page_size": page_limit,
        "total": total,
        "has_more": page_number * page_limit < total,
    }

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
        "profile_pic": get_profile_image_url(current_user.profile_pic),
        "role": role,
        "created_at": current_user.created_at,
        "stats": {"total_bookings": total_bookings},
        **extra,
    }
