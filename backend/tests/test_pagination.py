import os
import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

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
from routers import labs, tickets, users  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class PaginationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.admin = models.User(
            first_name="System",
            last_name="Admin",
            email="admin@example.test",
            password="hashed",
        )
        self.student = models.User(
            first_name="Test",
            last_name="Student",
            email="student@example.test",
            password="hashed",
        )
        self.admin_role = models.Role(name="admin")
        self.student_role = models.Role(name="student")
        self.lab = models.Lab(name="Test Lab", code="LAB01", capacity=20)
        self.session.add_all([
            self.admin,
            self.student,
            self.admin_role,
            self.student_role,
            self.lab,
        ])
        self.session.flush()
        self.admin.roles = [self.admin_role]
        self.student.roles = [self.student_role]

        created_at = datetime(2026, 9, 25, 12, 0)
        self.session.add_all([
            models.Ticket(
                user_id=self.student.id,
                subject=f"Ticket {index}",
                message="Test message",
                created_at=created_at + timedelta(minutes=index),
            )
            for index in range(5)
        ])
        self.session.add_all([
            models.Booking(
                lab_id=self.lab.id,
                user_id=self.student.id,
                booking_date=date(2026, 9, 24),
                start_time=time(8, 40),
                end_time=time(11, 0),
                purpose="history",
                total_participants=1,
                created_at=created_at,
            ),
            models.Booking(
                lab_id=self.lab.id,
                user_id=self.student.id,
                booking_date=date(2026, 9, 26),
                start_time=time(8, 40),
                end_time=time(11, 0),
                purpose="upcoming 1",
                total_participants=1,
                created_at=created_at + timedelta(minutes=1),
            ),
            models.Booking(
                lab_id=self.lab.id,
                user_id=self.student.id,
                booking_date=date(2026, 9, 27),
                start_time=time(12, 0),
                end_time=time(14, 20),
                purpose="upcoming 2",
                total_participants=1,
                created_at=created_at + timedelta(minutes=2),
            ),
        ])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_ticket_pagination_returns_page_metadata_and_stable_order(self):
        result = tickets.get_tickets(
            self.admin,
            self.session,
            page=2,
            page_size=2,
        )

        self.assertEqual(result["total"], 5)
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["page_size"], 2)
        self.assertTrue(result["has_more"])
        self.assertEqual([ticket.subject for ticket in result["data"]], [
            "Ticket 2",
            "Ticket 1",
        ])

    def test_user_and_booking_lists_page_on_the_server(self):
        user_result = users.get_all_users(
            self.admin,
            self.session,
            page=2,
            page_size=1,
        )
        self.assertEqual(user_result["total"], 2)
        self.assertEqual([user["email"] for user in user_result["data"]], [
            self.student.email,
        ])

        with patch.object(labs, "mark_due_no_shows"), patch.object(
            labs,
            "_lab_now",
            return_value=datetime(2026, 9, 25, 12, 0),
        ):
            result = labs.get_user_bookings(
                self.student.email,
                self.student,
                self.session,
                scope="upcoming",
                page=2,
                page_size=1,
            )

        self.assertEqual(result["scope"], "upcoming")
        self.assertEqual(result["total"], 2)
        self.assertFalse(result["has_more"])
        self.assertEqual([booking["purpose"] for booking in result["data"]], [
            "upcoming 1",
        ])


if __name__ == "__main__":
    unittest.main()
