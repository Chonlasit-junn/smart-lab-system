from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import date
from password_policy import validate_new_password



# --- Auth ---

class OTPRequest(BaseModel):
    email: EmailStr

class OTPVerify(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str


class PasswordReset(OTPVerify):
    new_password: str = Field(..., min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def validate_password_policy(cls, value):
        return validate_new_password(value)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Labs ---

class LabCreate(BaseModel):
    name: str = Field(..., max_length=80, example="Mac Lab")
    code: str = Field(..., max_length=32, example="LAB01")
    capacity: int = Field(40, gt=0)
    location: Optional[str] = Field(None, max_length=120)

class LabUpdate(BaseModel):
    name: str = Field(..., max_length=80)
    code: str = Field(..., max_length=32)
    capacity: int = Field(..., gt=0)
    location: Optional[str] = Field(None, max_length=120)

class LabStatusUpdate(BaseModel):
    status: str = Field(..., example="active")

class LabCapacityUpdate(BaseModel):
    capacity: int = Field(..., ge=0)


# --- Schedules ---

class ScheduleCreate(BaseModel):
    lab_id: int
    course_code: str = Field(..., max_length=32, example="CS101")
    course_name: str = Field(..., max_length=120, example="Introduction to Programming")
    instructor_name: str = Field(..., max_length=100, example="Dr. Smith")
    day_of_week: str = Field(..., max_length=16, example="Monday")
    slot_number: int = Field(..., ge=1, le=4)
    semester: str = Field(..., max_length=16, example="1")
    academic_year: str = Field(..., max_length=16, example="2026")
    valid_from: date
    valid_until: date


# --- Bookings ---

class BookingCreate(BaseModel):
    lab_id: int
    booking_date: date
    slot_number: int = Field(..., ge=1, le=4)
    # Legacy compatibility only. The booking owner is always resolved from
    # the authenticated Bearer token, never from client-supplied identity.
    email: Optional[EmailStr] = None
    purpose: Optional[str] = None
    total_participants: int = Field(1, gt=0)


# --- Tickets ---
# user_id มาจาก access token ไม่รับจาก client
class TicketCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1, max_length=5000)

# รูปแบบข้อมูลสำหรับการอัปเดตสถานะโดย Admin
class TicketUpdateStatus(BaseModel):
    status: str = Field(..., min_length=1) # เช่น "closed", "in_progress"


class TicketReplyCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    status: str | None = Field(default=None, max_length=24)
    # Retained for clients that still use the original reply payload.
    is_resolved: bool | None = None

# รูปแบบข้อมูลที่ API จะส่งกลับไปให้ Frontend
class TicketResponse(BaseModel):
    id: int
    user_id: int
    subject: str
    message: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
