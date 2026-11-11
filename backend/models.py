from sqlalchemy import BigInteger, CheckConstraint, Column, Float, Index, Integer, String, DateTime, Boolean, ForeignKey, Date, Time, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


# SQLite integration tests use INTEGER for autoincrementing primary keys;
# PostgreSQL uses the BIGINT types already present in the deployed schema.
BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class UserOTP(Base):
    __tablename__ = "user_otps"

    id = Column(Integer, primary_key=True)
    email = Column(String, index=True, nullable=False)
    otp_code = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RegistrationOTP(Base):
    """One current challenge per canonical email; legacy OTP rows are untouched."""

    __tablename__ = "registration_otps"
    __table_args__ = (
        CheckConstraint(
            "failed_attempts BETWEEN 0 AND 5 AND window_attempts BETWEEN 0 AND 5",
            name="registration_otps_attempts_check",
        ),
        CheckConstraint(
            "email = lower(trim(email)) AND trim(email) <> ''",
            name="registration_otps_email_check",
        ),
        {"info": {"manual_migration": True}},
    )

    email = Column(String, primary_key=True)
    challenge_id = Column(String(32), nullable=True)
    code_hash = Column(String(64), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    last_sent_at = Column(DateTime(timezone=True), nullable=True)
    failed_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    window_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    attempt_window_started_at = Column(DateTime(timezone=True), nullable=True)


class PasswordResetOTP(Base):
    __tablename__ = "password_reset_otps"
    __table_args__ = (
        CheckConstraint(
            "failed_attempts BETWEEN 0 AND 5 AND window_attempts BETWEEN 0 AND 5",
            name="password_reset_otps_attempts_check",
        ),
        CheckConstraint(
            "email = lower(trim(email)) AND trim(email) <> ''",
            name="password_reset_otps_email_check",
        ),
        {"info": {"manual_migration": True}},
    )

    email = Column(String, primary_key=True)
    challenge_id = Column(String(32), nullable=True)
    code_hash = Column(String(64), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    last_sent_at = Column(DateTime(timezone=True), nullable=True)
    failed_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    window_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    attempt_window_started_at = Column(DateTime(timezone=True), nullable=True)
    user_id = Column(BIGINT_ID, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    credential_hash = Column(String(64), nullable=True)


class OTPIPRateLimit(Base):
    """Hashed client identity and a short-lived OTP request counter."""

    __tablename__ = "otp_ip_rate_limits"
    __table_args__ = (
        CheckConstraint("request_count >= 0", name="otp_ip_rate_limits_request_count_check"),
        CheckConstraint("length(ip_hash) = 64", name="otp_ip_rate_limits_hash_length_check"),
        {"info": {"manual_migration": True}},
    )

    ip_hash = Column(String(64), primary_key=True)
    window_started_at = Column(DateTime(timezone=True), nullable=False)
    request_count = Column(Integer, nullable=False, default=0, server_default="0")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email = lower(trim(email)) AND trim(email) <> ''",
            name="users_email_canonical_check",
        ),
        CheckConstraint(
            "trim(first_name) <> '' AND trim(last_name) <> ''",
            name="users_names_nonblank_check",
        ),
    )

    id = Column(BIGINT_ID, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    auth_version = Column(Integer, nullable=False, default=0, server_default="0")
    profile_pic = Column(String, nullable=True)
    face_embedding = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    roles = relationship("Role", secondary="user_roles", back_populates="users")
    bookings = relationship("Booking", back_populates="user", cascade="all, delete-orphan")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (Index("idx_students_user_id", "user_id", unique=True),)

    id = Column(BIGINT_ID, primary_key=True)
    student_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(BIGINT_ID, ForeignKey("users.id"), nullable=False)
    faculty = Column(String, nullable=True)     # คณะ
    department = Column(String, nullable=True)  # สาขาวิชา
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserPassport(Base):
    # guest users only — is_active=False means pending admin approval
    __tablename__ = "user_passport"
    __table_args__ = (Index("idx_user_passport_user_id", "user_id", unique=True),)

    id = Column(BIGINT_ID, primary_key=True)
    user_id = Column(BIGINT_ID, ForeignKey("users.id"), nullable=False)
    phone = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Role(Base):
    __tablename__ = "roles"

    id = Column(BIGINT_ID, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    users = relationship("User", secondary="user_roles", back_populates="roles")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id = Column(BIGINT_ID, ForeignKey("users.id"), primary_key=True)
    role_id = Column(BIGINT_ID, ForeignKey("roles.id"), primary_key=True)


class Lab(Base):
    __tablename__ = "labs"
    __table_args__ = (
        CheckConstraint("capacity IS NULL OR capacity >= 0", name="labs_capacity_nonnegative_check"),
        CheckConstraint(
            "status IS NULL OR status IN ('active', 'inactive', 'maintenance')",
            name="labs_status_check",
        ),
    )

    id = Column(BIGINT_ID, primary_key=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, index=True, nullable=False)
    capacity = Column(Integer, default=0)
    location = Column(String, nullable=True)
    status = Column(String, default="active")  # active | inactive | maintenance
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    bookings = relationship("Booking", back_populates="lab", cascade="all, delete-orphan")
    schedules = relationship("ClassSchedule", back_populates="lab", cascade="all, delete-orphan")
    devices = relationship("LabDevice", back_populates="lab", cascade="all, delete-orphan")


class LabDevice(Base):
    """A workstation provisioned to one Lab by an administrator."""

    __tablename__ = "lab_devices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'maintenance', 'revoked')",
            name="lab_devices_status_check",
        ),
    )

    id = Column(Integer, primary_key=True)
    device_id = Column(String(128), unique=True, index=True, nullable=False)
    lab_id = Column(BIGINT_ID, ForeignKey("labs.id"), nullable=False, index=True)
    device_name = Column(String(255), nullable=False)
    device_mac = Column(String(64), nullable=True)
    status = Column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )  # active | maintenance | revoked
    agent_token_hash = Column(String(64), unique=True, nullable=False)
    agent_version = Column(String(64), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    lab = relationship("Lab", back_populates="devices")


class LabDeviceEnrollment(Base):
    """Short-lived, one-time code used to provision a workstation."""

    __tablename__ = "lab_device_enrollments"

    id = Column(Integer, primary_key=True)
    lab_id = Column(BIGINT_ID, ForeignKey("labs.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    used_device_id = Column(String(128), nullable=True)
    created_by = Column(BIGINT_ID, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BlacklistedApp(Base):
    __tablename__ = "blacklisted_apps"
    __table_args__ = (
        CheckConstraint(
            "match_type IN ('process_name', 'process_name_or_title', 'exe_path', 'window_title', 'website_domain')",
            name="blacklisted_apps_match_type_check",
        ),
    )

    id = Column(Integer, primary_key=True)
    app_name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    match_type = Column(
        String,
        nullable=False,
        default="process_name_or_title",
        server_default="process_name_or_title",
    )
    match_value = Column(String, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LabAccessLog(Base):
    __tablename__ = "lab_access_logs"
    __table_args__ = (
        CheckConstraint(
            "session_status IN ('active', 'completed', 'abandoned')",
            name="lab_access_logs_session_status_check",
        ),
        CheckConstraint(
            "(session_status = 'active' AND exit_time IS NULL) OR "
            "(session_status IN ('completed', 'abandoned') AND exit_time IS NOT NULL)",
            name="lab_access_logs_session_time_check",
        ),
        CheckConstraint(
            "exit_time IS NULL OR exit_time >= entry_time",
            name="lab_access_logs_time_order_check",
        ),
        CheckConstraint(
            "access_type IN ('entry', 'manual')",
            name="lab_access_logs_access_type_check",
        ),
        CheckConstraint(
            "status IN ('success', 'denied')",
            name="lab_access_logs_status_check",
        ),
        Index(
            "uq_active_session_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("session_status = 'active' AND exit_time IS NULL"),
            sqlite_where=text("session_status = 'active' AND exit_time IS NULL"),
        ),
        Index(
            "uq_active_session_per_lab_device",
            "lab_device_id",
            unique=True,
            postgresql_where=text(
                "lab_device_id IS NOT NULL AND session_status = 'active' AND exit_time IS NULL"
            ),
            sqlite_where=text(
                "lab_device_id IS NOT NULL AND session_status = 'active' AND exit_time IS NULL"
            ),
        ),
        Index(
            "uq_active_session_per_mac",
            text("lower(trim(device_mac))"),
            unique=True,
            postgresql_where=text(
                "session_status = 'active' AND exit_time IS NULL "
                "AND device_mac IS NOT NULL AND trim(device_mac) <> ''"
            ),
            sqlite_where=text(
                "session_status = 'active' AND exit_time IS NULL "
                "AND device_mac IS NOT NULL AND trim(device_mac) <> ''"
            ),
        ),
        Index(
            "uq_lab_access_logs_client_session_id",
            "client_session_id",
            unique=True,
            postgresql_where=text("client_session_id IS NOT NULL AND btrim(client_session_id) <> ''"),
            sqlite_where=text("client_session_id IS NOT NULL AND trim(client_session_id) <> ''"),
        ),
    )

    id = Column(BIGINT_ID, primary_key=True)
    lab_id = Column(BIGINT_ID, ForeignKey("labs.id"), nullable=False)
    user_id = Column(BIGINT_ID, ForeignKey("users.id"), nullable=False)
    booking_id = Column(BIGINT_ID, ForeignKey("bookings.id"), nullable=True)
    entry_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    exit_time = Column(DateTime(timezone=True), nullable=True)
    access_type = Column(String, nullable=False)  # entry | manual
    status = Column(String, nullable=False)        # success | denied
    lab_device_id = Column(Integer, ForeignKey("lab_devices.id"), nullable=True)
    device_used = Column(String, nullable=True)
    device_mac = Column(String, nullable=True)
    client_session_id = Column(String, nullable=True)
    session_status = Column(
        Text,
        nullable=False,
        default="active",
        server_default="active",
    )  # active | completed | abandoned
    end_reason = Column(Text, nullable=True)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    booking = relationship("Booking", back_populates="access_logs")
    lab_device = relationship("LabDevice")


class GatekeeperScanLog(Base):
    """Door-scan decisions, including attempts without a recognized user."""

    __tablename__ = "gatekeeper_scan_logs"
    __table_args__ = (
        CheckConstraint("decision IN ('granted', 'denied')", name="gatekeeper_scan_logs_decision_check"),
        CheckConstraint(
            "liveness_score IS NULL OR (liveness_score >= 0 AND liveness_score <= 1)",
            name="gatekeeper_scan_logs_liveness_check",
        ),
        {"info": {"manual_migration": True}},
    )

    id = Column(BIGINT_ID, primary_key=True)
    lab_id = Column(BIGINT_ID, ForeignKey("labs.id", ondelete="SET NULL"), nullable=True)
    lab_code = Column(String, nullable=False)
    # Preserve the authenticated camera's public ID even if it is later removed.
    device_id = Column(String(128), nullable=True)
    user_id = Column(BIGINT_ID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    booking_id = Column(BIGINT_ID, ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True)
    decision = Column(String(16), nullable=False)
    reason_code = Column(String(64), nullable=False)
    liveness_score = Column(Float, nullable=True)
    face_distance = Column(Float, nullable=True)
    scanned_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProgramUsageLog(Base):
    __tablename__ = "program_usage_logs"
    __table_args__ = (
        CheckConstraint("usage_end_time >= usage_start_time", name="program_usage_logs_time_order_check"),
        CheckConstraint("duration_seconds >= 0", name="program_usage_logs_duration_nonnegative_check"),
        Index(
            "uq_program_usage_logs_event_id",
            "event_id",
            unique=True,
            postgresql_where=text("event_id IS NOT NULL AND btrim(event_id) <> ''"),
            sqlite_where=text("event_id IS NOT NULL AND trim(event_id) <> ''"),
        ),
    )

    id = Column(BIGINT_ID, primary_key=True)
    lab_access_log_id = Column(BIGINT_ID, ForeignKey("lab_access_logs.id"), nullable=False)
    program_name = Column(String, nullable=False)
    usage_start_time = Column(DateTime(timezone=True), nullable=False)
    usage_end_time = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Integer, nullable=False, default=0)
    event_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UsageViolation(Base):
    """Immutable audit record for a forbidden application detected in a session."""

    __tablename__ = "usage_violations"
    __table_args__ = (
        Index(
            "uq_usage_violations_event_id",
            "event_id",
            unique=True,
            postgresql_where=text("event_id IS NOT NULL AND btrim(event_id) <> ''"),
            sqlite_where=text("event_id IS NOT NULL AND trim(event_id) <> ''"),
        ),
    )

    id = Column(BIGINT_ID, primary_key=True)
    lab_access_log_id = Column(
        BIGINT_ID,
        ForeignKey("lab_access_logs.id"),
        nullable=False,
    )
    program_usage_log_id = Column(
        BIGINT_ID,
        ForeignKey("program_usage_logs.id"),
        nullable=True,
    )
    program_name = Column(String, nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason = Column(Text, nullable=True)
    action_taken = Column(String, nullable=False, default="logout")
    event_id = Column(String, nullable=True)
    process_name = Column(String, nullable=True)
    exe_path = Column(Text, nullable=True)
    window_title = Column(Text, nullable=True)
    detection_source = Column(String, nullable=True)
    policy_version = Column(String, nullable=True)
    matched_rule_id = Column(BigInteger, nullable=True)


class ClassSchedule(Base):
    __tablename__ = "class_schedules"
    __table_args__ = (
        CheckConstraint("start_time < end_time", name="class_schedules_time_order_check"),
        CheckConstraint("valid_from <= valid_until", name="class_schedules_date_order_check"),
    )

    id = Column(BIGINT_ID, primary_key=True)
    lab_id = Column(BIGINT_ID, ForeignKey("labs.id"), nullable=False)
    course_code = Column(String, index=True, nullable=False)
    course_name = Column(String, nullable=True)
    instructor_name = Column(String, nullable=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    day_of_week = Column(String, nullable=False)  # Monday, Tuesday, ...
    semester = Column(String, nullable=False)
    academic_year = Column(String, nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    lab = relationship("Lab", back_populates="schedules")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("total_participants > 0", name="bookings_participants_positive_check"),
        CheckConstraint("start_time < end_time", name="bookings_time_order_check"),
        CheckConstraint(
            "status IN ('reserved', 'attended', 'completed', 'cancelled', 'no_show')",
            name="bookings_status_check",
        ),
    )

    id = Column(BIGINT_ID, primary_key=True)
    lab_id = Column(BIGINT_ID, ForeignKey("labs.id"), nullable=False)
    user_id = Column(BIGINT_ID, ForeignKey("users.id"), nullable=False)
    booking_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    purpose = Column(Text, nullable=True)
    total_participants = Column(Integer, nullable=False, default=1)
    status = Column(
        String,
        nullable=False,
        default="reserved",
        server_default="reserved",
        index=True,
    )  # reserved | attended | completed | cancelled | no_show
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    checked_out_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String, nullable=True)
    no_show_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="bookings")
    lab = relationship("Lab", back_populates="bookings")
    access_logs = relationship("LabAccessLog", back_populates="booking")


class UserDailyScore(Base):
    __tablename__ = "user_daily_scores"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="user_daily_scores_range_check"),
    )

    user_id = Column(BIGINT_ID, ForeignKey("users.id"), primary_key=True)
    score_date = Column(Date, primary_key=True)
    score = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User", backref="daily_scores")


class UserPoints(Base):
    __tablename__ = "user_points"
    __table_args__ = (
        CheckConstraint("points BETWEEN 0 AND 100", name="user_points_range_check"),
    )

    user_id    = Column(BIGINT_ID, ForeignKey("users.id"), primary_key=True)
    points     = Column(Integer, default=100, nullable=False)  # เริ่มที่ 100
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User", backref="points_record")


class PointPolicy(Base):
    """The single Admin-managed configuration for the point system."""

    __tablename__ = "point_policies"
    __table_args__ = (
        CheckConstraint("id = 1", name="point_policies_singleton_check"),
        CheckConstraint(
            "daily_bonus BETWEEN 0 AND 10 AND complete_session BETWEEN 0 AND 20 "
            "AND no_show BETWEEN -100 AND 0 AND forbidden_app BETWEEN -100 AND 0 "
            "AND late_cancel BETWEEN -100 AND 0 AND point_request_amount BETWEEN 1 AND 100 "
            "AND warning_threshold BETWEEN 0 AND 100 "
            "AND ban_level_1_below BETWEEN 1 AND 100 AND ban_level_1_days BETWEEN 0 AND 365 "
            "AND ban_level_2_below BETWEEN 1 AND 100 AND ban_level_2_days BETWEEN 0 AND 365 "
            "AND ban_level_3_below BETWEEN 1 AND 100 AND ban_level_3_days BETWEEN 0 AND 365 "
            "AND ban_level_4_below BETWEEN 1 AND 100 AND ban_level_4_days BETWEEN 0 AND 365",
            name="point_policies_value_ranges_check",
        ),
        CheckConstraint(
            "ban_level_1_below < ban_level_2_below "
            "AND ban_level_2_below < ban_level_3_below "
            "AND ban_level_3_below < ban_level_4_below",
            name="point_policies_threshold_order_check",
        ),
    )

    id = Column(Integer, primary_key=True, default=1)
    daily_bonus = Column(Integer, nullable=False, default=1)
    complete_session = Column(Integer, nullable=False, default=2)
    no_show = Column(Integer, nullable=False, default=-5)
    forbidden_app = Column(Integer, nullable=False, default=-10)
    late_cancel = Column(Integer, nullable=False, default=-3)
    point_request_amount = Column(Integer, nullable=False, default=10)
    warning_threshold = Column(Integer, nullable=False, default=20)
    ban_level_1_below = Column(Integer, nullable=False, default=20)
    ban_level_1_days = Column(Integer, nullable=False, default=30)
    ban_level_2_below = Column(Integer, nullable=False, default=40)
    ban_level_2_days = Column(Integer, nullable=False, default=7)
    ban_level_3_below = Column(Integer, nullable=False, default=60)
    ban_level_3_days = Column(Integer, nullable=False, default=5)
    ban_level_4_below = Column(Integer, nullable=False, default=80)
    ban_level_4_days = Column(Integer, nullable=False, default=2)
    updated_by = Column(BIGINT_ID, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PointLog(Base):
    __tablename__ = "point_logs"
    __table_args__ = (
        Index(
            "uq_point_logs_event_id",
            "event_id",
            unique=True,
            postgresql_where=text("event_id IS NOT NULL AND btrim(event_id) <> ''"),
            sqlite_where=text("event_id IS NOT NULL AND trim(event_id) <> ''"),
        ),
    )

    id         = Column(Integer, primary_key=True)
    user_id    = Column(BIGINT_ID, ForeignKey("users.id"), nullable=False)
    change     = Column(Integer, nullable=False)   # -5, +1 etc.
    reason     = Column(String, nullable=False)    # point event reason
    note       = Column(String, nullable=True)     # รายละเอียดเพิ่ม เช่น ชื่อโปรแกรมที่โดน detect
    event_id   = Column(String, nullable=True)
    source_type = Column(String, nullable=True)
    source_id = Column(BigInteger, nullable=True)
    points_before = Column(Integer, nullable=True)
    points_after = Column(Integer, nullable=True)
    daily_score_before = Column(Integer, nullable=True)
    daily_score_after = Column(Integer, nullable=True)
    score_date = Column(Date, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PointRequest(Base):
    __tablename__ = "point_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="point_requests_status_check",
        ),
        CheckConstraint(
            "requested_points BETWEEN 1 AND 100",
            name="point_requests_amount_check",
        ),
        Index(
            "uq_point_requests_pending_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(BIGINT_ID, ForeignKey("users.id"), nullable=False, index=True)
    requested_points = Column(Integer, nullable=False, default=10, server_default="10")
    status = Column(
        String,
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )  # pending | approved | rejected
    user_message = Column(Text, nullable=True)
    admin_note = Column(Text, nullable=True)
    reviewed_by = Column(BIGINT_ID, ForeignKey("users.id"), nullable=True, index=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class BanRecord(Base):
    __tablename__ = "ban_records"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(BIGINT_ID, ForeignKey("users.id"), nullable=False)
    ban_until  = Column(DateTime(timezone=True), nullable=False)
    reason     = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True)
    user_id = Column(BIGINT_ID, ForeignKey("users.id"), index=True)
    subject = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default="open") # สถานะเริ่มต้นคือ open
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TicketReply(Base):
    """Admin replies and resolution updates visible to the ticket owner."""

    __tablename__ = "ticket_replies"
    __table_args__ = (
        CheckConstraint("length(trim(message)) > 0 AND length(message) <= 5000", name="ticket_replies_message_check"),
        CheckConstraint("status IN ('received', 'in_progress', 'resolved')", name="ticket_replies_status_check"),
        {"info": {"manual_migration": True}},
    )

    id = Column(BIGINT_ID, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    admin_id = Column(BIGINT_ID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    responder_name = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="in_progress", server_default="in_progress")
    is_resolved = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
