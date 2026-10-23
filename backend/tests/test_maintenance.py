import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR)) if str(BACKEND_DIR) not in sys.path else None
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import models  # noqa: E402
from database import Base  # noqa: E402
from maintenance import cleanup_expired_data  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class ExpiredDataCleanupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        required_tables = {"users", "labs", "registration_otps", "password_reset_otps",
                           "otp_ip_rate_limits", "lab_device_enrollments"}
        tables = [table for table in Base.metadata.sorted_tables if table.name in required_tables]
        Base.metadata.create_all(self.engine, tables=tables)
        self.db = sessionmaker(bind=self.engine)()
        self.now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        user = models.User(
            first_name="Cleanup", last_name="Test", email="cleanup@example.test", password="hash",
        )
        lab = models.Lab(name="Cleanup Lab", code="CLEANUP", capacity=1)
        self.db.add_all([user, lab])
        self.db.flush()
        self.user_id = user.id
        self.lab_id = lab.id
        self.db.add_all([
            models.RegistrationOTP(email="old1@example.test", expires_at=self.now - timedelta(seconds=1)),
            models.RegistrationOTP(email="old2@example.test", expires_at=self.now - timedelta(seconds=2)),
            models.RegistrationOTP(email="current@example.test", expires_at=self.now + timedelta(minutes=5)),
            models.PasswordResetOTP(email="reset@example.test", expires_at=self.now - timedelta(seconds=1)),
            models.OTPIPRateLimit(ip_hash="a" * 64, window_started_at=self.now - timedelta(minutes=11), request_count=30),
            models.OTPIPRateLimit(ip_hash="b" * 64, window_started_at=self.now - timedelta(minutes=2), request_count=2),
            models.LabDeviceEnrollment(
                lab_id=self.lab_id, token_hash="unused-expired", expires_at=self.now - timedelta(seconds=1),
                created_by=self.user_id,
            ),
            models.LabDeviceEnrollment(
                lab_id=self.lab_id, token_hash="used-expired", expires_at=self.now - timedelta(seconds=1),
                used_at=self.now - timedelta(minutes=1), used_device_id="device-1", created_by=self.user_id,
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_cleanup_is_expiry_scoped_bounded_and_preserves_used_enrollments(self):
        with patch("maintenance.utc_now", return_value=self.now):
            first = cleanup_expired_data(self.db, batch_size=1)
            second = cleanup_expired_data(self.db, batch_size=1)

        self.assertEqual(first["deleted"]["registration_otps"], 1)
        self.assertTrue(first["has_more"]["registration_otps"])
        self.assertEqual(second["deleted"]["registration_otps"], 1)
        self.assertFalse(second["has_more"]["registration_otps"])
        self.assertEqual(self.db.query(models.RegistrationOTP).count(), 1)
        self.assertEqual(self.db.query(models.PasswordResetOTP).count(), 0)
        self.assertEqual(self.db.query(models.OTPIPRateLimit).count(), 1)
        self.assertEqual(self.db.query(models.LabDeviceEnrollment).count(), 1)
        self.assertEqual(self.db.query(models.LabDeviceEnrollment).one().used_device_id, "device-1")

    def test_cleanup_enforces_hard_batch_ceiling(self):
        with self.assertRaises(ValueError):
            cleanup_expired_data(self.db, batch_size=501)


if __name__ == "__main__":
    unittest.main()
