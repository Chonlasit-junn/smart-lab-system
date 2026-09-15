from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from datetime import date




# --- Auth ---

class OTPRequest(BaseModel):
    email: EmailStr

class OTPVerify(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Users --- 
class UserBasicInfo(BaseModel):
    id: int
    first_name: str
    last_name: str

    class Config:
        from_attributes = True

# --- Labs ---

class LabCreate(BaseModel):
    name: str = Field(..., example="Mac Lab")
    code: str = Field(..., example="LAB01")
    capacity: int = Field(40, gt=0)
    location: Optional[str] = None

class LabUpdate(BaseModel):
    name: str
    code: str
    capacity: int = Field(..., gt=0)
    location: Optional[str] = None

class LabStatusUpdate(BaseModel):
    status: str = Field(..., example="active")

class LabCapacityUpdate(BaseModel):
    capacity: int = Field(..., ge=0)


# --- Schedules ---

class ScheduleCreate(BaseModel):
    lab_id: int
    course_code: str = Field(..., example="CS101")
    course_name: str = Field(..., example="Introduction to Programming")
    instructor_name: str = Field(..., example="Dr. Smith")
    day_of_week: str = Field(..., example="Monday")
    slot_number: int = Field(..., ge=1, le=4)
    semester: str = Field(..., example="1")
    academic_year: str = Field(..., example="2026")
    valid_from: date
    valid_until: date


# --- Bookings ---

class BookingCreate(BaseModel):
    lab_id: int
    booking_date: date
    slot_number: int = Field(..., ge=1, le=4)
    email: EmailStr
    purpose: Optional[str] = None
    total_participants: int = Field(1, gt=0)


# --- Tickets ---
# รูปแบบข้อมูลที่ User จะส่งมาตอนสร้าง Ticket
class TicketBase(BaseModel):
    subject: str
    message: str

class TicketCreate(TicketBase):
    pass  # ไม่ต้องรับ user_id จาก client แล้ว จะดึงจาก token แทน

# อัปเดต TicketResponse ให้มีข้อมูล user แนบไปด้วย
class TicketResponse(TicketBase):
    id: int
    user_id: int
    status: str
    created_at: Optional[datetime] = None
    
    # เพิ่มบรรทัดนี้เพื่อดึง object ของ UserBasicInfo มาด้วย
    user: Optional[UserBasicInfo] = None

    class Config:
        from_attributes = True

class TicketUpdateStatus(BaseModel):
    status: str = Field(..., example="closed")