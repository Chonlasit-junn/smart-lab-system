import os
import sys

import models
from database import SessionLocal, engine
from password_policy import validate_new_password
from sqlalchemy.orm import Session
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_ROLES = [
    {"name": "admin",   "display_name": "Administrator"},
    {"name": "student", "display_name": "University Student"},
    {"name": "guest",   "display_name": "Guest User"},
]

DEFAULT_LABS = [
    {
        "name": "Smart Lab Center 1",
        "code": "LAB01",
        "capacity": 30,
        "location": "Building 5, Room 501",
        "status": "active",
    }
]

ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD")


class SeedConfigurationError(ValueError):
    """A safe, actionable seed configuration error that contains no secrets."""


DEFAULT_BLACKLIST = [
    {
        "app_name": "BitTorrent",
        "description": "ไม่อนุญาตให้ใช้โปรแกรมสำหรับดาวน์โหลดหรือแลกเปลี่ยนไฟล์ที่อาจละเมิดลิขสิทธิ์ภายในห้องปฏิบัติการ",
        "match_type": "process_name",
        "match_value": "bittorrent",
        "enabled": True,
    },
    {
        "app_name": "CheatEngine",
        "description": "ไม่อนุญาตให้ใช้โปรแกรมสำหรับแก้ไขหรือดัดแปลงหน่วยความจำของโปรแกรมภายในห้องปฏิบัติการ",
        "match_type": "process_name",
        "match_value": "cheatengine",
        "enabled": True,
    },
    {
        "app_name": "GenshinImpact",
        "description": "ไม่อนุญาตให้ใช้โปรแกรมเกม Genshin Impact ระหว่างการใช้งานห้องปฏิบัติการ",
        "match_type": "process_name",
        "match_value": "genshinimpact",
        "enabled": True,
    },
    {
        "app_name": "StarRail",
        "description": "ไม่อนุญาตให้ใช้โปรแกรมเกม Honkai: Star Rail ระหว่างการใช้งานห้องปฏิบัติการ",
        "match_type": "process_name",
        "match_value": "starrail",
        "enabled": True,
    },
]


def seed_roles(db: Session) -> None:
    for role_data in DEFAULT_ROLES:
        exists = db.query(models.Role).filter(models.Role.name == role_data["name"]).first()
        if not exists:
            db.add(models.Role(**role_data))
            print(f"  + role: {role_data['name']}")


def seed_labs(db: Session) -> None:
    for lab_data in DEFAULT_LABS:
        exists = db.query(models.Lab).filter(models.Lab.code == lab_data["code"]).first()
        if not exists:
            db.add(models.Lab(**lab_data))
            print(f"  + lab: {lab_data['code']}")


def seed_blacklisted_apps(db: Session) -> None:
    for app in DEFAULT_BLACKLIST:
        existing = db.query(models.BlacklistedApp).filter(
            models.BlacklistedApp.app_name == app["app_name"]
        ).first()
        if not existing:
            db.add(models.BlacklistedApp(**app))
            print(f"  + blacklist: {app['app_name']}")
        else:
            # Preserve Admin-managed descriptions and enabled state.
            old_match_value = (existing.match_value or existing.app_name).strip().casefold()
            seed_match_value = app["match_value"].strip().casefold()
            if (
                existing.match_type == "process_name_or_title"
                and old_match_value == seed_match_value
            ):
                # Upgrade only untouched legacy defaults to the Agent's current
                # process-name rule type; preserve customized rules.
                existing.match_type = app["match_type"]


def seed_users(db: Session) -> None:
    admin_email = "admin@smartlab.com"
    admin_role = db.query(models.Role).filter(models.Role.name == "admin").first()
    admin_user = db.query(models.User).filter(models.User.email == admin_email).first()
    created_admin = admin_user is None
    if not admin_user:
        if not ADMIN_PASSWORD:
            raise SeedConfigurationError(
                "SEED_ADMIN_PASSWORD is required to create the admin user."
            )
        try:
            validate_new_password(ADMIN_PASSWORD)
        except ValueError:
            raise SeedConfigurationError(
                "SEED_ADMIN_PASSWORD does not meet the current password policy."
            ) from None
        admin_user = models.User(
            first_name="System",
            last_name="Admin",
            email=admin_email,
            password=pwd_context.hash(ADMIN_PASSWORD),
        )
        db.add(admin_user)
        db.flush()
        print(f"  + admin: {admin_email}")

    if admin_role and admin_role not in admin_user.roles:
        if not created_admin:
            raise SeedConfigurationError(
                "Existing admin@smartlab.com account lacks the admin role; "
                "Seed will not promote an existing account automatically."
            )
        admin_user.roles.append(admin_role)

    points_record = db.query(models.UserPoints).filter(
        models.UserPoints.user_id == admin_user.id,
    ).first()
    if not points_record:
        db.add(models.UserPoints(user_id=admin_user.id, points=100))
        print(f"  + initial points: {admin_user.email}")


def seed_data() -> None:
    print("Running seed...")
    db = SessionLocal()
    try:
        # Match backend startup: SQL migrations own these tables and constraints.
        models.Base.metadata.create_all(
            bind=engine,
            tables=[
                table
                for table in models.Base.metadata.sorted_tables
                if not table.info.get("manual_migration")
            ],
        )
        seed_roles(db)
        seed_labs(db)
        seed_blacklisted_apps(db)
        db.flush()  # flush before seed_users so roles are available for lookup

        seed_users(db)

        db.commit()
        print("Seed complete.")
    except SeedConfigurationError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise RuntimeError(
            "Seed failed; transaction rolled back. Check database settings and migrations."
        ) from None
    finally:
        db.close()


if __name__ == "__main__":
    try:
        seed_data()
    except (SeedConfigurationError, RuntimeError) as error:
        print(f"Seed failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
