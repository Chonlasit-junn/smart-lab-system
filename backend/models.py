from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Date, Time, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from database import Base

# ==============================================================================
# AUTHENTICATION & USER MANAGEMENT
# ==============================================================================

class UserOTP(Base):
    """Stores temporary OTPs for user registration and verification."""
    __tablename__ = "user_otps"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    otp_code = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class User(Base):
    """Core user account details."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    profile_pic = Column(String, nullable=True)     
    face_embedding = Column(JSONB, nullable=True) # Facial recognition vector data
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Student(Base):
    """Extended profile specific to university students."""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class UserPassport(Base):
    """Extended profile for external or guest users."""
    __tablename__ = "user_passport"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    phone = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# ==============================================================================
# ROLE-BASED ACCESS CONTROL (RBAC)
# ==============================================================================

class Role(Base):
    """Defines system roles (e.g., admin, student, guest)."""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class UserRole(Base):
    """Mapping table for User and Role (Many-to-Many)."""
    __tablename__ = "user_roles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)

# ==============================================================================
# LABORATORY & RESOURCE MANAGEMENT
# ==============================================================================

class Lab(Base):
    """Master data for laboratory rooms."""
    __tablename__ = "labs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, index=True, nullable=False)
    capacity = Column(Integer, default=0)
    location = Column(String, nullable=True)
    status = Column(String, default="active") # Expected values: 'active', 'disabled', 'maintenance'
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class BlacklistedApp(Base):
    """List of restricted applications monitored by the hardware agent."""
    __tablename__ = "blacklisted_apps"

    id = Column(Integer, primary_key=True, index=True)
    app_name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# ==============================================================================
# MONITORING & LOGGING
# ==============================================================================

class LabAccessLog(Base):
    """Records physical or system entry and exit events for a lab session."""
    __tablename__ = "lab_access_logs"

    id = Column(Integer, primary_key=True, index=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    entry_time = Column(DateTime(timezone=True), server_default=func.now())
    exit_time = Column(DateTime(timezone=True), nullable=True)
    access_type = Column(String, nullable=False) # e.g., 'face', 'manual'
    status = Column(String, nullable=False)      # e.g., 'success', 'violation'
    device_used = Column(String, nullable=True)  # Hardware identifier or hostname

class ProgramUsageLog(Base):
    """Records specific software usage duration during a lab session."""
    __tablename__ = "program_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    lab_access_log_id = Column(Integer, ForeignKey("lab_access_logs.id"), nullable=False)
    program_name = Column(String, nullable=False)
    usage_start_time = Column(DateTime(timezone=True), nullable=False)
    usage_end_time = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# ==============================================================================
# SCHEDULING & BOOKING SYSTEM
# ==============================================================================

class ClassSchedule(Base):
    """Fixed academic schedules that block standard lab availability."""
    __tablename__ = "class_schedules"

    id = Column(Integer, primary_key=True, index=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=False)
    course_code = Column(String, index=True, nullable=False)
    course_name = Column(String, nullable=True)
    instructor_name = Column(String, nullable=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    day_of_week = Column(String, nullable=False) # e.g., 'Monday', 'Tuesday'
    semester = Column(String, nullable=False)
    academic_year = Column(String, nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Booking(Base):
    """Student seat or room reservations."""
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    booking_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    purpose = Column(Text, nullable=True)
    total_participants = Column(Integer, nullable=False, default=1)
    status = Column(String, default="pending") # Expected values: 'pending', 'approved', 'rejected', 'cancelled'
    created_at = Column(DateTime(timezone=True), server_default=func.now())