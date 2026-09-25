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
from routers import admin as admin_router  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class AdminDashboardTests(unittest.TestCase):
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
        self.pending_guest = models.User(
            first_name="Pending",
            last_name="Guest",
            email="guest@example.test",
            password="hashed",
        )
        self.lab = models.Lab(name="Test Lab", code="LAB01", capacity=20)
        self.session.add_all([self.admin, self.student, self.pending_guest, self.lab])
        self.session.flush()
        self.session.add(models.UserPassport(user_id=self.pending_guest.id, is_active=False))

        base_created_at = datetime(2026, 9, 25, 8, 0)
        for index in range(12):
            self.session.add(
                models.Booking(
                    lab_id=self.lab.id,
                    user_id=self.student.id,
                    booking_date=date(2026, 9, 25),
                    start_time=time(8, 40),
                    end_time=time(11, 0),
                    created_at=base_created_at + timedelta(minutes=index),
                )
            )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_dashboard_returns_aggregate_counts_and_only_latest_ten_bookings(self):
        with patch.object(admin_router, "mark_due_no_shows") as mark_due_no_shows:
            result = admin_router.get_dashboard_summary(self.admin, self.session)

        data = result["data"]
        self.assertEqual(data["total_requests"], 12)
        self.assertEqual(data["active_users"], 3)
        self.assertEqual(data["pending_approvals"], 1)
        self.assertEqual(len(data["recent_reservations"]), 10)
        self.assertEqual(
            [booking["id"] for booking in data["recent_reservations"]],
            list(range(12, 2, -1)),
        )
        self.assertEqual(data["recent_reservations"][0]["user"]["id"], self.student.id)
        self.assertEqual(data["recent_reservations"][0]["lab"]["code"], "LAB01")
        mark_due_no_shows.assert_called_once()


if __name__ == "__main__":
    unittest.main()
