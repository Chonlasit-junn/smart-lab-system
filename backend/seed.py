import models
from database import SessionLocal, engine
from sqlalchemy.orm import Session

# ============================================================================
# 1. INITIAL DATA (ข้อมูลตั้งต้น)
# ============================================================================

DEFAULT_ROLES = [
    {"name": "admin", "display_name": "Administrator"},
    {"name": "student", "display_name": "University Student"},
    {"name": "guest", "display_name": "Guest User"}
]

DEFAULT_LABS = [
    {
        "name": "Smart Lab Center 1",
        "code": "LAB01",
        "capacity": 30,
        "location": "Building 5, Room 501",
        "status": "open"
    }
]

DEFAULT_BLACKLIST = [
    {"app_name": "BitTorrent", "description": "ห้ามใช้โปรแกรมโหลดไฟล์ละเมิดลิขสิทธิ์"},
    {"app_name": "CheatEngine", "description": "ห้ามใช้โปรแกรมดัดแปลงหน่วยความจำ"},
    {"app_name": "GenshinImpact", "description": "ไม่อนุญาตให้เล่นเกม Genshin ขณะใช้งานห้องแล็บ"},
    {"app_name": "StarRail", "description": "ไม่อนุญาตให้ขึ้นรถไฟ Star Rail ในเวลาเรียนครับกัปตัน!"}
]

# ============================================================================
# 2. SEED FUNCTIONS (ฟังก์ชันจัดการข้อมูล)
# ============================================================================

def seed_roles(db: Session) -> None:
    """
    ตรวจสอบและเพิ่มข้อมูล Role เริ่มต้นลงในฐานข้อมูล
    
    Args:
        db (Session): Database session
    """
    print("🌱 กำลังตรวจสอบข้อมูล Role...")
    for role_data in DEFAULT_ROLES:
        existing_role = db.query(models.Role).filter(models.Role.name == role_data["name"]).first()
        if not existing_role:
            db.add(models.Role(**role_data))
            print(f"✅ เพิ่ม Role: {role_data['name']}")

def seed_labs(db: Session) -> None:
    """
    ตรวจสอบและเพิ่มข้อมูลห้องแล็บเริ่มต้น
    
    Args:
        db (Session): Database session
    """
    print("🏫 กำลังตรวจสอบข้อมูลห้องแล็บ...")
    for lab_data in DEFAULT_LABS:
        existing_lab = db.query(models.Lab).filter(models.Lab.code == lab_data["code"]).first()
        if not existing_lab:
            db.add(models.Lab(**lab_data))
            print(f"✅ เพิ่ม Lab: {lab_data['code']}")

def seed_blacklisted_apps(db: Session) -> None:
    """
    ตรวจสอบและเพิ่มรายชื่อโปรแกรมต้องห้าม (Blacklist)
    หากมีแอปนี้อยู่แล้ว จะทำการอัปเดตคำอธิบายให้เป็นเวอร์ชันล่าสุด
    
    Args:
        db (Session): Database session
    """
    print("🛡️  กำลังตรวจสอบข้อมูล Blacklist...")
    for app in DEFAULT_BLACKLIST:
        existing_app = db.query(models.BlacklistedApp).filter(models.BlacklistedApp.app_name == app["app_name"]).first()
        if not existing_app:
            db.add(models.BlacklistedApp(**app))
            print(f"✅ เพิ่ม Blacklist: {app['app_name']}")
        else:
            existing_app.description = app["description"]

# ============================================================================
# 3. MAIN EXECUTION
# ============================================================================

def seed_data() -> None:
    """
    ฟังก์ชันหลักสำหรับรันกระบวนการ Seed ข้อมูลทั้งหมด
    จัดการเรื่องการสร้างตาราง การเรียกใช้ฟังก์ชันย่อย และดูแล Transaction (Commit/Rollback)
    """
    print("🏗️  กำลังตรวจสอบโครงสร้างตาราง...")
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # เรียกใช้ฟังก์ชันแยกย่อยทีละส่วน
        seed_roles(db)
        seed_labs(db)
        seed_blacklisted_apps(db)
        
        # บันทึกข้อมูลทั้งหมดลงฐานข้อมูล
        db.commit()
        
        print("\n" + "="*40)
        print("🎉 เสร็จสิ้นการเตรียมข้อมูลฐานระบบ (Seed Complete!)")
        print("="*40)
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดระหว่าง Seed ข้อมูล: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()