import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt
from passlib.context import CryptContext
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from dotenv import load_dotenv

# โหลด .env ใน utils เองด้วย เพื่อให้แน่ใจว่า mail_config ได้ค่าจริงก่อนถูกสร้าง
load_dotenv()

UPLOAD_DIR = "uploads/profiles"
os.makedirs(UPLOAD_DIR, exist_ok=True)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# in production these should all come from .env — never hardcode in source
SECRET_KEY = os.getenv("SECRET_KEY", "SmartLab_Super_Secret_Key_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

mail_config = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", "auth.smartlab.noreply@gmail.com"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
    MAIL_FROM=os.getenv("MAIL_FROM", "auth.smartlab.noreply@gmail.com"),
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def send_otp_mail(email: str, otp: str) -> None:
    body = (
        f"Your verification code is: {otp}\n\n"
        f"This code will expire in 5 minutes. Please do not share it with anyone."
    )
    message = MessageSchema(
        subject="OTP Verification for Smart Lab Project",
        recipients=[email],
        body=body,
        subtype=MessageType.plain,
    )
    await FastMail(mail_config).send_message(message)