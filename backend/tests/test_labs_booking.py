import os
import sys
import unittest
from datetime import date, datetime, time, timedelta
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
import schemas  # noqa: E402
from database import Base  # noqa: E402
from routers import labs, users  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class LabBookingLogicTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.user = models.User(
            first_name="Test",
            last_name="Student",
            email="student@example.com",
            password="hashed",
        )
        self.session.add(self.user)
        self.session.flush()
        self.session.add(models.UserPoints(user_id=self.user.id, points=100))
        self.lab = models.Lab(
            name="Test Lab",
            code="LAB-TEST",
            capacity=10,
            status="active",
        )
        self.session.add(self.lab)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _future_date(self, weekday_name):
        candidate = date.today() + timedelta(days=1)
        while candidate.strftime("%A") != weekday_name:
            candidate += timedelta(days=1)
        return candidate

    def _schedule(self, target_date, day_of_week="Monday", slot_number=1):
        slot = labs.VALID_TIME_SLOTS[slot_number]
        schedule = models.ClassSchedule(
            lab_id=self.lab.id,
            course_code="CS-TEST",
            course_name="Testing",
            instructor_name="Tester",
            start_time=slot["start"],
            end_time=slot["end"],
            day_of_week=day_of_week,
            semester="1",
            academic_year=str(target_date.year),
            valid_from=target_date,
            valid_until=target_date,
        )
        self.session.add(schedule)
        self.session.commit()
        return schedule

    def test_availability_blocks_legacy_weekday_format(self):
        target_date = self._future_date("Monday")
        self._schedule(target_date, day_of_week=" monday ", slot_number=1)

        result = labs.check_availability(self.lab.id, target_date, self.session)

        self.assertEqual(result["slots"][1]["status"], "class")
        self.assertEqual(result["slots"][2]["status"], "available")

    def test_booking_rejects_a_scheduled_class_even_when_weekday_is_thai(self):
        target_date = self._future_date("Monday")
        self._schedule(target_date, day_of_week="วันจันทร์", slot_number=1)
        payload = schemas.BookingCreate(
            lab_id=self.lab.id,
            booking_date=target_date,
            slot_number=1,
            email=self.user.email,
            purpose="test",
            total_participants=1,
        )
        fake_now = datetime.combine(
            target_date - timedelta(days=1),
            time(8, 0),
        )

        with patch.object(labs, "_lab_now", return_value=fake_now):
            with self.assertRaises(HTTPException) as context:
                labs.create_booking(payload, self.user, self.session)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("scheduled class", str(context.exception.detail))

    def test_booking_owner_comes_from_authenticated_user_without_client_email(self):
        target_date = date.today() + timedelta(days=2)
        payload = schemas.BookingCreate(
            lab_id=self.lab.id,
            booking_date=target_date,
            slot_number=1,
            purpose="test",
            total_participants=1,
        )
        fake_now = datetime.combine(
            target_date - timedelta(days=1),
            time(8, 0),
        )

        with patch.object(labs, "_lab_now", return_value=fake_now):
            result = labs.create_booking(payload, self.user, self.session)

        booking = self.session.query(models.Booking).filter(
            models.Booking.id == result["booking_id"],
        ).one()
        self.assertEqual(result["user_id"], self.user.id)
        self.assertEqual(booking.user_id, self.user.id)

    def test_schedule_validation_rejects_reversed_date_range(self):
        payload = schemas.ScheduleCreate(
            lab_id=self.lab.id,
            course_code="CS-TEST",
            course_name="Testing",
            instructor_name="Tester",
            day_of_week="Monday",
            slot_number=1,
            semester="1",
            academic_year="2026",
            valid_from=date(2026, 9, 20),
            valid_until=date(2026, 9, 19),
        )

        with self.assertRaises(HTTPException) as context:
            labs._validate_schedule_input(payload, self.session)

        self.assertEqual(context.exception.status_code, 422)

    def test_schedule_validation_rejects_overlapping_legacy_time_range(self):
        target_date = self._future_date("Monday")
        self.session.add(models.ClassSchedule(
            lab_id=self.lab.id,
            course_code="CS-LEGACY",
            course_name="Legacy schedule",
            instructor_name="Tester",
            start_time=time(9, 0),
            end_time=time(10, 0),
            day_of_week=" monday ",
            semester=" 1 ",
            academic_year=" 2026 ",
            valid_from=target_date,
            valid_until=target_date,
        ))
        self.session.commit()

        payload = schemas.ScheduleCreate(
            lab_id=self.lab.id,
            course_code="CS-NEW",
            course_name="New course",
            instructor_name="Tester",
            day_of_week="Monday",
            slot_number=1,
            semester="1",
            academic_year="2026",
            valid_from=target_date,
            valid_until=target_date,
        )

        with self.assertRaises(HTTPException) as context:
            labs._validate_schedule_input(payload, self.session)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("conflicts", str(context.exception.detail))

    def test_admin_dependency_rejects_non_admin(self):
        with self.assertRaises(HTTPException) as context:
            users.require_admin_user(self.user, self.session)

        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
