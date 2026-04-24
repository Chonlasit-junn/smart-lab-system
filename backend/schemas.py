from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import date

# ============================================================================
# PHASE 0: AUTHENTICATION & USER MANAGEMENT
# ============================================================================

class OTPRequest(BaseModel):
    """Schema สำหรับร้องขอ OTP เบื้องต้น"""
    email: EmailStr

class OTPVerify(BaseModel):
    """Schema สำหรับยืนยัน OTP ก่อนเข้าสู่ขั้นตอนตั้งรหัสผ่าน"""
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, description="รหัส OTP 6 หลัก")

class UserRegister(BaseModel):
    """Schema สำหรับลงทะเบียนสร้างบัญชีใหม่"""
    email: EmailStr
    otp: str
    password: str = Field(..., min_length=6, description="รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
    name: str
    
    # Optional สำหรับคนทั่วไป (Guest) ที่ไม่มีรหัสนิสิต/คณะ
    student_id: Optional[str] = Field(None, description="รหัสนิสิต/นักศึกษา (เฉพาะนักศึกษา)")
    faculty: Optional[str] = Field(None, description="คณะ (เฉพาะนักศึกษา)")
    department: Optional[str] = Field(None, description="สาขาภาควิชา (เฉพาะนักศึกษา)")

class UserLogin(BaseModel):
    """Schema สำหรับเข้าสู่ระบบ"""
    email: EmailStr
    password: str

class Token(BaseModel):
    """Schema สำหรับส่ง JWT Token กลับไปยัง Client หลังล็อกอินสำเร็จ"""
    access_token: str
    token_type: str = "bearer"


# ============================================================================
# PHASE 1: LABORATORY MANAGEMENT (Lab Master)
# ============================================================================

class LabCreate(BaseModel):
    """Schema สำหรับแอดมินสร้างข้อมูลห้องแล็บใหม่"""
    name: str = Field(..., example="Mac Lab")
    code: str = Field(..., example="LAB01", description="รหัสอ้างอิงห้องแล็บ (ห้ามซ้ำ)")
    capacity: int = Field(40, gt=0, description="ความจุที่นั่งเริ่มต้น (ค่า Default คือ 40)")
    location: Optional[str] = Field(None, example="ตึก 1 ชั้น 5")

class LabUpdate(BaseModel):
    """Schema สำหรับแก้ไขข้อมูลห้องแล็บทั้งหมด"""
    name: str
    code: str
    capacity: int = Field(..., gt=0)
    location: Optional[str] = None

class LabStatusUpdate(BaseModel):
    """Schema สำหรับเปิด/ปิดการจองห้องแล็บ (Toggle Status)"""
    status: str = Field(..., example="active", description="รับเฉพาะค่า 'active', 'disabled', หรือ 'maintenance'")

class LabCapacityUpdate(BaseModel):
    """Schema สำหรับปรับลดจำนวนที่นั่งชั่วคราว (เช่น คอมพิวเตอร์เสีย)"""
    capacity: int = Field(..., ge=0, description="จำนวนที่นั่งที่ใช้งานได้จริง ณ ปัจจุบัน")


# ============================================================================
# PHASE 2: CLASS SCHEDULE MANAGEMENT
# ============================================================================

class ScheduleCreate(BaseModel):
    """Schema สำหรับแอดมินนำเข้าตารางเรียน (บล็อกเวลาจากการจองของนักศึกษา)"""
    lab_id: int
    course_code: str = Field(..., example="CS101")
    course_name: str = Field(..., example="Introduction to Programming")
    instructor_name: str = Field(..., example="ดร. สมชาย")
    day_of_week: str = Field(..., example="Monday", description="วันในสัปดาห์ เช่น Monday - Sunday")
    
    # 🌟 บังคับให้รับค่าแค่ 1-4 เท่านั้น (ge = greater than or equal, le = less than or equal)
    slot_number: int = Field(..., ge=1, le=4, description="คาบเรียน (1: เช้า, 2: เที่ยง, 3: บ่าย, 4: เย็น)")
    
    semester: str = Field(..., example="1", description="ภาคเรียน เช่น 1, 2, Summer")
    academic_year: str = Field(..., example="2026", description="ปีการศึกษา")
    valid_from: date = Field(..., description="วันที่เปิดเทอม (เริ่มล็อกตารางนี้)")
    valid_until: date = Field(..., description="วันที่ปิดเทอม (สิ้นสุดการล็อกตารางนี้)")


# ============================================================================
# PHASE 3: SMART BOOKING SYSTEM
# ============================================================================

class BookingCreate(BaseModel):
    """Schema สำหรับผู้ใช้ส่งคำขอจองที่นั่งในห้องแล็บ"""
    lab_id: int
    booking_date: date = Field(..., description="วันที่ต้องการจอง")
    
    # 🌟 บังคับให้รับค่าแค่ 1-4 เท่านั้น
    slot_number: int = Field(..., ge=1, le=4, description="คาบเวลาที่ต้องการจอง (1-4)")
    email: EmailStr = Field(..., description="อีเมลของผู้ใช้งานที่จอง (เพื่อเชื่อมโยงกับ User ID)")
    purpose: Optional[str] = Field(None, example="ทำโปรเจกต์จบ", description="เหตุผลการจองห้อง")
    total_participants: int = Field(1, gt=0, description="จำนวนผู้ใช้งาน (Default = 1)")