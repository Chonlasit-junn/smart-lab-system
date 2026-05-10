import models
from database import SessionLocal, engine
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

DEFAULT_BLACKLIST = [
    {"app_name": "BitTorrent",    "description": "ห้ามใช้โปรแกรมโหลดไฟล์ละเมิดลิขสิทธิ์"},
    {"app_name": "CheatEngine",   "description": "ห้ามใช้โปรแกรมดัดแปลงหน่วยความจำ"},
    {"app_name": "GenshinImpact", "description": "ไม่อนุญาตให้เล่นเกม Genshin ขณะใช้งานห้องแล็บ"},
    {"app_name": "StarRail",      "description": "ไม่อนุญาตให้ขึ้นรถไฟ Star Rail ในเวลาเรียนครับกัปตัน!"},
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
            # update description in case we changed the wording
            existing.description = app["description"]


def seed_users(db: Session) -> None:
    admin_email = "admin@smartlab.com"
    if db.query(models.User).filter(models.User.email == admin_email).first():
        return  # already exists, skip

    admin_role = db.query(models.Role).filter(models.Role.name == "admin").first()
    admin_user = models.User(
        first_name="System",
        last_name="Admin",
        email=admin_email,
        password=pwd_context.hash("admin1234"),
    )
    if admin_role:
        admin_user.roles.append(admin_role)
    db.add(admin_user)
    print(f"  + admin: {admin_email}")


def seed_data() -> None:
    print("Running seed...")
    models.Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_roles(db)
        seed_labs(db)
        seed_blacklisted_apps(db)
        db.flush()  # flush before seed_users so roles are available for lookup

        seed_users(db)

        db.commit()
        print("Seed complete.")
    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()