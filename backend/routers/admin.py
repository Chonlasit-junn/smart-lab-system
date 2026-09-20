from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel, Field
import models
from database import get_db
from routers.users import require_admin_user
from profile_storage import delete_profile_image_sync, get_profile_image_url

router = APIRouter(prefix="/admin", tags=["Admin"])


class VerifyAction(BaseModel):
    action: str = Field(..., description="'approve' or 'reject'")


SYSTEM_ROLE_NAMES = {"admin", "student", "guest"}
ROLE_PRIORITY = {"admin": 0, "student": 1, "guest": 2}


class RoleDisplayUpdate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=100)


class RoleAssignment(BaseModel):
    role_id: int = Field(..., gt=0)


def _primary_role(roles: list[models.Role]) -> models.Role | None:
    if not roles:
        return None
    return min(roles, key=lambda role: ROLE_PRIORITY.get(role.name, 99))


def _serialize_role(role: models.Role, user_count: int = 0) -> dict:
    return {
        "id": role.id,
        "name": role.name,
        "display_name": role.display_name or role.name,
        "user_count": user_count,
        "is_system": role.name in SYSTEM_ROLE_NAMES,
        "assignable": role.name in SYSTEM_ROLE_NAMES,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


def _serialize_role_user(user: models.User) -> dict:
    roles = sorted(
        user.roles,
        key=lambda role: ROLE_PRIORITY.get(role.name, 99),
    )
    primary_role = _primary_role(roles)
    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "created_at": user.created_at,
        "role": primary_role.name if primary_role else "guest",
        "role_display_name": (
            primary_role.display_name if primary_role and primary_role.display_name else
            primary_role.name if primary_role else "Guest User"
        ),
        "roles": [
            {
                "id": role.id,
                "name": role.name,
                "display_name": role.display_name or role.name,
            }
            for role in roles
        ],
    }


@router.get("/roles")
def get_roles(
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    counts = dict(
        db.query(models.UserRole.role_id, func.count(models.UserRole.user_id))
        .group_by(models.UserRole.role_id)
        .all()
    )
    roles = db.query(models.Role).order_by(models.Role.id.asc()).all()
    return {
        "data": [_serialize_role(role, counts.get(role.id, 0)) for role in roles],
    }


@router.get("/roles/users")
def get_role_users(
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    users = (
        db.query(models.User)
        .options(selectinload(models.User.roles))
        .order_by(models.User.id.asc())
        .all()
    )
    return {"data": [_serialize_role_user(user) for user in users]}


@router.put("/roles/{role_id}")
def update_role_display_name(
    role_id: int,
    payload: RoleDisplayUpdate,
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")

    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="Role display name cannot be empty.")

    role.display_name = display_name
    db.commit()
    db.refresh(role)
    user_count = db.query(models.UserRole).filter(models.UserRole.role_id == role.id).count()
    return {"data": _serialize_role(role, user_count)}


@router.put("/roles/users/{user_id}")
def assign_user_role(
    user_id: int,
    payload: RoleAssignment,
    current_admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role.")

    user = (
        db.query(models.User)
        .options(selectinload(models.User.roles))
        .filter(models.User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    role = db.query(models.Role).filter(models.Role.id == payload.role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    if role.name not in SYSTEM_ROLE_NAMES:
        raise HTTPException(
            status_code=400,
            detail="This role is not available for user assignment yet.",
        )

    currently_admin = any(existing.name == "admin" for existing in user.roles)
    if currently_admin and role.name != "admin":
        admin_count = (
            db.query(models.UserRole)
            .join(models.Role, models.Role.id == models.UserRole.role_id)
            .filter(models.Role.name == "admin")
            .count()
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="At least one Admin account must remain in the system.",
            )

    user.roles = [role]
    db.commit()
    db.refresh(user)
    return {"data": _serialize_role_user(user), "message": "User role updated."}


@router.get("/users/pending")
def get_pending_users(
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
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
                "profile_pic": get_profile_image_url(user.profile_pic),
                "phone": passport.phone,
                "created_at": user.created_at,
            }
            for user, passport in pending
        ]
    }


@router.put("/users/{user_id}/verify")
def verify_user(
    user_id: int,
    payload: VerifyAction,
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    passport = db.query(models.UserPassport).filter(models.UserPassport.user_id == user_id).first()

    if not user or not passport:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.action == "approve":
        passport.is_active = True
        db.commit()
        return {"message": "User approved successfully."}

    elif payload.action == "reject":
        profile_image_path = user.profile_pic
        # delete child records first, then flush so FK constraints are satisfied
        # before we delete the parent user row
        db.delete(passport)
        db.query(models.UserRole).filter(models.UserRole.user_id == user.id).delete()
        db.flush()
        db.delete(user)
        db.commit()
        delete_profile_image_sync(profile_image_path)
        return {"message": "User rejected and removed."}

    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'.")
