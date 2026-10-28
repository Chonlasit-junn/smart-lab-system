import os
import httpx
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from jose import jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
from security_config import SECRET_KEY, ALGORITHM

load_dotenv()

# Keep uploaded biometric data outside the source tree while preserving the
# public URL prefix stored in the database (uploads/profiles/<file>).  A
# deployment can override the physical storage location with an absolute
# SMART_LAB_UPLOAD_DIR path.
BACKEND_DIR = Path(__file__).resolve().parent
configured_upload_root = Path(
    os.getenv("SMART_LAB_UPLOAD_DIR") or "runtime/uploads"
).expanduser()
UPLOAD_ROOT = (
    configured_upload_root
    if configured_upload_root.is_absolute()
    else BACKEND_DIR / configured_upload_root
)
UPLOAD_DIR = str(UPLOAD_ROOT / "profiles")
PROFILE_URL_PREFIX = "uploads/profiles"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=False,
)

# in production these should all come from .env
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# --- ดึงค่า Brevo จาก Environment ---
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "smartlab@example.com") # ใช้อีเมลที่สมัคร Brevo


def normalize_email(value: Any) -> str:
    """Use one canonical form for email comparisons across the API."""

    return str(value or "").strip().casefold()


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# 📌 ฟังก์ชันส่งอีเมลผ่าน HTTP API ของ Brevo
async def send_otp_mail(email: str, otp: str, *, password_reset: bool = False) -> None:
    if not BREVO_API_KEY:
        raise RuntimeError("OTP mail provider is not configured.")

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    
    # โครงสร้างข้อมูลที่ Brevo ต้องการ
    payload = {
        "sender": {
            "name": "Smart Lab System",
            "email": SENDER_EMAIL
        },
        "to": [
            {"email": email}
        ],
        "subject": "Reset your Smart Lab password" if password_reset else "OTP Verification for Smart Lab Project",
        "htmlContent": f"""
        <div style="font-family: sans-serif; max-width: 500px; margin: 0 auto;">
            <h2 style="color: #2563eb;">{'Smart Lab Password Reset' if password_reset else 'Smart Lab Verification'}</h2>
            <p>{'Use this code only to reset your password. If you did not request this, ignore this email.' if password_reset else 'Your verification code is:'}</p>
            <h1 style="background: #f1f5f9; padding: 10px; border-radius: 8px; text-align: center; letter-spacing: 5px; color: #1e293b;">{otp}</h1>
            <p style="color: #64748b; font-size: 14px;">This code will expire in 10 minutes. Please do not share it with anyone.</p>
        </div>
        """
    }

    # ยิง Request ออกไปหา Brevo ด้วย HTTPS (ไม่โดนบล็อกพอร์ต 100%)
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status() # ถ้าพัง จะเด้งไปเข้า except
        except httpx.HTTPError:
            raise RuntimeError("OTP mail delivery failed.") from None
