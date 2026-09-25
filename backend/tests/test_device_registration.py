import os
import sys
import unittest
from datetime import date, datetime, time, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import models  # noqa: E402
from database import Base  # noqa: E402
from routers import agent, devices  # noqa: E402
from device_registry import hash_device_token, require_registered_device  # noqa: E402
from routers.users import require_admin_user  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class DeviceRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.admin = models.User(
            first_name="System",
            last_name="Admin",
            email="admin@example.com",
            password="hashed",
        )
        self.role = models.Role(name="admin", display_name="Administrator")
        self.session.add_all([self.admin, self.role])
        self.session.flush()
        self.session.add(models.UserRole(user_id=self.admin.id, role_id=self.role.id))
        self.lab = models.Lab(name="Test Lab", code="LAB-TEST", capacity=20, status="active")
        self.session.add(self.lab)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_enrollment_code_registers_and_authenticates_device_once(self):
        code_result = devices.create_enrollment_code(
            devices.EnrollmentCodeCreate(lab_id=self.lab.id, expires_in_minutes=10),
            self.admin,
            self.session,
        )

        result = devices.register_device(
            enrollment_code=code_result["enrollment_code"],
            device_id="device-test-001",
            device_name="LAB-PC-01",
            device_mac="AA:BB:CC:DD:EE:FF",
            agent_version="source",
            db=self.session,
        )

        registered = require_registered_device(
            self.session,
            result["device_id"],
            result["device_token"],
        )
        self.assertEqual(registered.lab_id, self.lab.id)
        self.assertEqual(result["device"]["lab"]["code"], "LAB-TEST")

        with self.assertRaises(HTTPException) as context:
            devices.register_device(
                enrollment_code=code_result["enrollment_code"],
                device_id="device-test-002",
                device_name="LAB-PC-02",
                db=self.session,
            )
        self.assertEqual(context.exception.status_code, 409)

    def test_admin_can_register_directly_without_an_enrollment_code(self):
        payload = devices.AdminDeviceRegister(
            lab_id=self.lab.id,
            device_id="device-direct-001",
            device_name="LAB-PC-DIRECT",
            device_mac="AA:BB:CC:DD:EE:FF",
            agent_version="source",
        )

        result = devices.register_device_as_admin(payload, self.admin, self.session)

        stored_device = self.session.query(models.LabDevice).filter(
            models.LabDevice.device_id == result["device_id"],
        ).one()
        self.assertEqual(result["device"]["lab"]["id"], self.lab.id)
        self.assertEqual(result["device"]["device_name"], "LAB-PC-DIRECT")
        self.assertNotEqual(stored_device.agent_token_hash, result["device_token"])
        self.assertEqual(
            stored_device.agent_token_hash,
            hash_device_token(result["device_token"]),
        )
        self.assertEqual(
            require_registered_device(
                self.session,
                result["device_id"],
                result["device_token"],
            ).lab_id,
            self.lab.id,
        )

    def test_admin_registration_route_requires_admin_dependency(self):
        route = next(
            route
            for route in devices.router.routes
            if getattr(route, "path", None) == "/admin/lab-devices/register"
        )

        self.assertTrue(
            any(dependency.call is require_admin_user for dependency in route.dependant.dependencies)
        )

    def test_direct_registration_rejects_inactive_labs(self):
        self.lab.status = "maintenance"
        self.session.commit()
        payload = devices.AdminDeviceRegister(
            lab_id=self.lab.id,
            device_id="device-direct-002",
            device_name="LAB-PC-DIRECT",
        )

        with self.assertRaises(HTTPException) as context:
            devices.register_device_as_admin(payload, self.admin, self.session)

        self.assertEqual(context.exception.status_code, 409)

    def test_revoked_device_credential_is_rejected(self):
        code_result = devices.create_enrollment_code(
            devices.EnrollmentCodeCreate(lab_id=self.lab.id),
            self.admin,
            self.session,
        )
        result = devices.register_device(
            enrollment_code=code_result["enrollment_code"],
            device_id="device-test-003",
            device_name="LAB-PC-03",
            agent_version=None,
            db=self.session,
        )
        device = self.session.query(models.LabDevice).filter(
            models.LabDevice.device_id == result["device_id"],
        ).one()
        device.status = "revoked"
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            require_registered_device(
                self.session,
                result["device_id"],
                result["device_token"],
            )
        self.assertEqual(context.exception.status_code, 403)

    def test_start_session_uses_registered_lab_not_client_lab_code(self):
        code_result = devices.create_enrollment_code(
            devices.EnrollmentCodeCreate(lab_id=self.lab.id),
            self.admin,
            self.session,
        )
        registration = devices.register_device(
            enrollment_code=code_result["enrollment_code"],
            device_id="device-test-004",
            device_name="LAB-PC-04",
            device_mac="11:22:33:44:55:66",
            agent_version="source",
            db=self.session,
        )
        student = models.User(
            first_name="Test",
            last_name="Student",
            email="student@example.com",
            password="hashed",
        )
        self.session.add(student)
        self.session.commit()

        result = agent.start_session(
            email=student.email,
            lab_code="A-DIFFERENT-LAB",
            device="LAB-PC-04",
            device_mac="11:22:33:44:55:66",
            device_id=registration["device_id"],
            device_token=registration["device_token"],
            agent_version="source",
            client_session_id="client-session-004",
            db=self.session,
        )

        access_log = self.session.query(models.LabAccessLog).filter(
            models.LabAccessLog.id == result["session_id"],
        ).one()
        device = self.session.query(models.LabDevice).filter(
            models.LabDevice.device_id == registration["device_id"],
        ).one()
        self.assertEqual(access_log.lab_id, self.lab.id)
        self.assertEqual(access_log.lab_device_id, device.id)

    def test_start_session_matches_booking_using_the_lab_calendar(self):
        code_result = devices.create_enrollment_code(
            devices.EnrollmentCodeCreate(lab_id=self.lab.id),
            self.admin,
            self.session,
        )
        registration = devices.register_device(
            enrollment_code=code_result["enrollment_code"],
            device_id="device-test-timezone",
            device_name="LAB-PC-TIMEZONE",
            device_mac="22:33:44:55:66:77",
            agent_version="source",
            db=self.session,
        )
        student = models.User(
            first_name="Time",
            last_name="Zone",
            email="timezone@example.com",
            password="hashed",
        )
        self.session.add(student)
        self.session.flush()
        booking = models.Booking(
            lab_id=self.lab.id,
            user_id=student.id,
            booking_date=date(2026, 9, 22),
            start_time=time(8, 40),
            end_time=time(11, 0),
            purpose="timezone test",
            total_participants=1,
            status="reserved",
        )
        self.session.add(booking)
        self.session.commit()

        with patch.object(
            agent,
            "lab_now_naive",
            return_value=datetime(2026, 9, 22, 9, 0),
        ), patch.object(
            agent,
            "utc_now",
            return_value=datetime(2026, 9, 22, 2, 0, tzinfo=timezone.utc),
        ), patch.object(agent, "mark_due_no_shows", return_value=0), patch.object(
            agent,
            "_cleanup_stale_sessions",
            return_value=0,
        ):
            agent.start_session(
                email=student.email,
                lab_code="A-DIFFERENT-LAB",
                device="LAB-PC-TIMEZONE",
                device_mac="22:33:44:55:66:77",
                device_id=registration["device_id"],
                device_token=registration["device_token"],
                agent_version="source",
                client_session_id="client-session-timezone",
                db=self.session,
            )

        self.session.refresh(booking)
        self.assertEqual(booking.status, "attended")
        checked_in_at = booking.checked_in_at
        if checked_in_at.tzinfo is None:
            checked_in_at = checked_in_at.replace(tzinfo=timezone.utc)
        self.assertEqual(
            checked_in_at,
            datetime(2026, 9, 22, 2, 0, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
