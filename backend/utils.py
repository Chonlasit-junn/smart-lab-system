import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt
from passlib.context import CryptContext
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

# ============================================================================
# 1. SYSTEM CONFIGURATION & SETUP
# ============================================================================

# --- Directory Setup ---
UPLOAD_DIR = "uploads/profiles"
os.makedirs(UPLOAD_DIR, exist_ok=True) 

# --- Security & JWT Setup ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# แนะนำ: ในการนำขึ้น Production จริง ควรตั้งค่าตัวแปรเหล่านี้ผ่านไฟล์ .env
SECRET_KEY = os.getenv("SECRET_KEY", "SmartLab_Super_Secret_Key_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 

# --- Email Configuration ---
mail_config = ConnectionConfig(
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "auth.smartlab.noreply@gmail.com"),
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "vsvdeyxtzhfedebb"), 
    MAIL_FROM = os.getenv("MAIL_FROM", "auth.smartlab.noreply@gmail.com"),
    MAIL_PORT = 587,
    MAIL_SERVER = "smtp.gmail.com",
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)

# ============================================================================
# 2. HELPER FUNCTIONS
# ============================================================================

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    สร้าง JWT Access Token สำหรับยืนยันตัวตนผู้ใช้
    
    Args:
        data (dict): ข้อมูลที่ต้องการฝังลงใน Token (Payload) เช่น email, role
        expires_delta (Optional[timedelta]): ระยะเวลาหมดอายุของ Token (ถ้าไม่ระบุ จะใช้ค่าเริ่มต้น 15 นาที)
        
    Returns:
        str: สตริง JWT Token ที่เข้ารหัสแล้ว
    """
    to_encode = data.copy()
    
    # กำหนดเวลาหมดอายุของ Token
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
        
    to_encode.update({"exp": expire})
    
    # เข้ารหัสข้อมูลและส่งกลับเป็นสตริง JWT
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def send_otp_mail(email: str, otp: str) -> None:
    """
    ส่งอีเมลแจ้งรหัส OTP ไปยังผู้ใช้งาน
    
    Args:
        email (str): ที่อยู่อีเมลปลายทาง
        otp (str): รหัส OTP 6 หลักที่สร้างจากระบบ
        
    Returns:
        None
    """
    email_body = (
        f"Your verification code is: {otp}\n\n"
        f"This code will expire in 5 minutes. Please do not share it with anyone."
    )
    
    message = MessageSchema(
        subject="OTP Verification for Smart Lab Project",
        recipients=[email],
        body=email_body,
        subtype=MessageType.plain
    )
    
    fm = FastMail(mail_config)
    await fm.send_message(message)