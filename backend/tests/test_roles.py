import os
import sys
import unittest
from pathlib import Path

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
from routers import admin as admin_router  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class RoleManagementTests(unittest.TestCase):
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
        self.student = models.User(
            first_name="Test",
            last_name="Student",
            email="student@example.com",
            password="hashed",
        )
        self.admin_role = models.Role(name="admin", display_name="Administrator")
        self.student_role = models.Role(name="student", display_name="University Student")
        self.guest_role = models.Role(name="guest", display_name="Guest User")
        self.session.add_all([
            self.admin,
            self.student,
            self.admin_role,
            self.student_role,
            self.guest_role,
        ])
        self.session.flush()
        self.admin.roles = [self.admin_role]
        self.student.roles = [self.student_role]
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_roles_include_assignment_counts(self):
        result = admin_router.get_roles(self.admin, self.session)
        counts = {item["name"]: item["user_count"] for item in result["data"]}

        self.assertEqual(counts["admin"], 1)
        self.assertEqual(counts["student"], 1)
        self.assertEqual(counts["guest"], 0)

    def test_admin_can_update_display_name_without_changing_role_key(self):
        result = admin_router.update_role_display_name(
            self.student_role.id,
            admin_router.RoleDisplayUpdate(display_name="ผู้เรียน"),
            self.admin,
            self.session,
        )

        self.assertEqual(result["data"]["name"], "student")
        self.assertEqual(result["data"]["display_name"], "ผู้เรียน")

    def test_admin_can_assign_an_existing_system_role(self):
        result = admin_router.assign_user_role(
            self.student.id,
            admin_router.RoleAssignment(role_id=self.guest_role.id),
            self.admin,
            self.session,
        )

        self.assertEqual(result["data"]["role"], "guest")
        self.assertEqual([role.name for role in self.student.roles], ["guest"])

    def test_admin_cannot_change_own_role(self):
        with self.assertRaises(HTTPException) as context:
            admin_router.assign_user_role(
                self.admin.id,
                admin_router.RoleAssignment(role_id=self.student_role.id),
                self.admin,
                self.session,
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_last_admin_cannot_be_demoted(self):
        acting_admin = models.User(id=999, email="other-admin@example.com")
        with self.assertRaises(HTTPException) as context:
            admin_router.assign_user_role(
                self.admin.id,
                admin_router.RoleAssignment(role_id=self.student_role.id),
                acting_admin,
                self.session,
            )

        self.assertEqual(context.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
