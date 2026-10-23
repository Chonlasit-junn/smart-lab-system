import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import models  # noqa: E402
from database import Base  # noqa: E402
from routers import points  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


TEST_TABLES = [
    Base.metadata.tables[name]
    for name in (
        "users",
        "roles",
        "user_roles",
        "user_points",
        "user_daily_scores",
        "point_policies",
        "point_logs",
        "point_requests",
        "ban_records",
    )
]


class AdminPointsPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=TEST_TABLES)
        self.session = sessionmaker(bind=self.engine)()
        self.today = date(2026, 9, 25)
        self.now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)

        self.admin = models.User(
            first_name="System",
            last_name="Admin",
            email="admin@example.test",
            password="hashed",
        )
        self.admin_role = models.Role(name="admin")
        self.student_role = models.Role(name="student")
        self.students = [
            models.User(
                first_name=f"Student{index}",
                last_name="Test",
                email=f"student{index}@example.test",
                password="hashed",
            )
            for index in range(5)
        ]
        self.session.add_all([self.admin, self.admin_role, self.student_role, *self.students])
        self.session.flush()
        self.admin.roles = [self.admin_role]

        for index, student in enumerate(self.students):
            student.roles = [self.student_role]
            self.session.add_all([
                models.UserPoints(user_id=student.id, points=75 + index),
                models.UserDailyScore(
                    user_id=student.id,
                    score_date=self.today,
                    score=80 + index,
                ),
                models.PointLog(
                    user_id=student.id,
                    change=1,
                    reason="daily_bonus",
                    event_id=f"daily:{student.id}:{self.today.isoformat()}",
                    points_before=74 + index,
                    points_after=75 + index,
                    daily_score_before=79 + index,
                    daily_score_after=80 + index,
                    score_date=self.today,
                    created_at=self.now,
                ),
            ])

        self.session.add_all([
            models.BanRecord(
                user_id=self.students[0].id,
                ban_until=self.now + timedelta(days=1),
                reason="active test ban",
            ),
            models.BanRecord(
                user_id=self.students[1].id,
                ban_until=self.now - timedelta(days=1),
                reason="expired test ban",
            ),
        ])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _get_admin_points(self):
        with (
            patch.object(points, "mark_due_no_shows", return_value=0),
            patch.object(points, "_business_today", return_value=self.today),
            patch.object(points, "_now_utc", return_value=self.now),
        ):
            return points.get_all_user_points(self.admin, self.session)

    def test_admin_points_batches_display_bans_and_daily_scores(self):
        statements = []

        def record_statement(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.casefold())

        event.listen(self.engine, "before_cursor_execute", record_statement)
        try:
            result = self._get_admin_points()
        finally:
            event.remove(self.engine, "before_cursor_execute", record_statement)

        users = result["data"]
        self.assertEqual(len(users), len(self.students))
        self.assertEqual([user["points"] for user in users], [75, 76, 77, 78, 79])
        self.assertEqual([user["daily_score"] for user in users], [80, 81, 82, 83, 84])
        self.assertTrue(users[0]["is_banned"])
        self.assertFalse(users[1]["is_banned"])
        self.assertEqual(result["summary"]["banned_users"], 1)

        daily_score_queries = [
            statement for statement in statements
            if "user_daily_scores" in statement
        ]
        page_queries = [
            statement for statement in statements
            if "limit" in statement and "offset" in statement
            and "from users" in statement
        ]
        # User rows, scores and active bans are joined in one paged query.
        self.assertEqual(len(daily_score_queries), 1)
        self.assertEqual(len(page_queries), 1)
        self.assertIn("limit", page_queries[0])
        self.assertIn("offset", page_queries[0])

    def test_admin_read_does_not_award_daily_bonus_to_every_user(self):
        self.session.query(models.PointLog).delete(synchronize_session=False)
        self.session.commit()

        first_result = self._get_admin_points()["data"]
        second_result = self._get_admin_points()["data"]

        self.assertEqual([user["points"] for user in first_result], [75, 76, 77, 78, 79])
        self.assertEqual([user["points"] for user in second_result], [75, 76, 77, 78, 79])
        self.assertEqual(self.session.query(models.PointLog).count(), 0)

    def test_admin_points_filters_search_and_paginates_in_database(self):
        result = points.get_all_user_points(
            self.admin,
            self.session,
            page=2,
            page_size=2,
            filter_mode="all",
            sort_by="pointsAsc",
        )
        self.assertEqual(result["total"], 5)
        self.assertEqual([row["points"] for row in result["data"]], [77, 78])
        self.assertEqual(result["summary"]["total_users"], 5)

        filtered = points.get_all_user_points(
            self.admin,
            self.session,
            search="student4@",
            filter_mode="banned",
            sort_by="name",
        )
        self.assertEqual(filtered["total"], 0)
        allowed = points.get_all_user_points(
            self.admin,
            self.session,
            search="student4@",
            filter_mode="allowed",
            sort_by="name",
        )
        self.assertEqual([row["email"] for row in allowed["data"]], ["student4@example.test"])

    def test_pending_recovery_request_keeps_legacy_points_account_behavior(self):
        student = self.students[0]
        self.session.query(models.UserPoints).filter_by(user_id=student.id).delete(
            synchronize_session=False,
        )
        self.session.add(models.PointRequest(
            user_id=student.id,
            requested_points=10,
            status="pending",
        ))
        self.session.commit()

        result = self._get_admin_points()
        student_result = next(
            user for user in result["data"] if user["user_id"] == student.id
        )

        self.assertEqual(student_result["points"], points.MAX_POINTS)
        self.assertEqual(student_result["daily_score"], 80)
        self.assertEqual(student_result["point_request"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
