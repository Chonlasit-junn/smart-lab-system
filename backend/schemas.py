from typing import Optional
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