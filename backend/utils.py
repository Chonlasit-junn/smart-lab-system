import os
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

UPLOAD_DIR = "uploads/profiles"
os.makedirs(UPLOAD_DIR, exist_ok=True)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=False,
)

# in production these should all come from .env
SECRET_KEY = os.getenv("SECRET_KEY", "SmartLab_Super_Secret_Key_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# --- ดึงค่า Brevo จาก Environment ---
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "smartlab@example.com") # ใช้อีเมลที่สมัคร Brevo

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# 📌 ฟังก์ชันส่งอีเมลผ่าน HTTP API ของ Brevo
async def send_otp_mail(email: str, otp: str) -> None:
    if not BREVO_API_KEY:
        print("❌ ERROR: BREVO_API_KEY is missing. Please set it in Hugging Face Secrets.")
        return

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
        "subject": "OTP Verification for Smart Lab Project",
        "htmlContent": f"""
        <div style="font-family: sans-serif; max-width: 500px; margin: 0 auto;">
            <h2 style="color: #2563eb;">Smart Lab Verification</h2>
            <p>Your verification code is:</p>
            <h1 style="background: #f1f5f9; padding: 10px; border-radius: 8px; text-align: center; letter-spacing: 5px; color: #1e293b;">{otp}</h1>
            <p style="color: #64748b; font-size: 14px;">This code will expire in 5 minutes. Please do not share it with anyone.</p>
        </div>
        """
    }

    # ยิง Request ออกไปหา Brevo ด้วย HTTPS (ไม่โดนบล็อกพอร์ต 100%)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status() # ถ้าพัง จะเด้งไปเข้า except
            print(f"✅ Email successfully sent to {email} via Brevo API")
        except httpx.HTTPStatusError as e:
            print(f"❌ Failed to send email: {e.response.text}")
            raise Exception(f"Failed to send email via API: {e.response.text}")
        except Exception as e:
            print(f"❌ Failed to connect to Brevo API: {e}")
            raise Exception(f"Failed to connect to email server: {str(e)}")