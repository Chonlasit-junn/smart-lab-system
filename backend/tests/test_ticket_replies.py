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
import schemas  # noqa: E402
from database import Base  # noqa: E402
from routers import tickets  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class TicketReplyTests(unittest.TestCase):
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
        self.other_student = models.User(
            first_name="Other",
            last_name="Student",
            email="other@example.test",
            password="hashed",
        )
        self.admin_role = models.Role(name="admin")
        self.student_role = models.Role(name="student")
        self.session.add_all([
            self.admin,
            self.student,
            self.other_student,
            self.admin_role,
            self.student_role,
        ])
        self.session.flush()
        self.admin.roles = [self.admin_role]
        self.student.roles = [self.student_role]
        self.other_student.roles = [self.student_role]
        self.ticket = models.Ticket(
            user_id=self.student.id,
            subject="Cannot book a lab",
            message="The available time list is empty.",
            status="open",
        )
        self.other_ticket = models.Ticket(
            user_id=self.other_student.id,
            subject="Other request",
            message="Private request.",
            status="open",
        )
        self.session.add_all([self.ticket, self.other_ticket])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_admin_reply_statuses_are_visible_to_ticket_owner(self):
        first = tickets.create_ticket_reply(
            self.ticket.id,
            schemas.TicketReplyCreate(message="We have received your request.", status="received"),
            self.admin,
            self.session,
        )
        self.assertFalse(first["data"]["is_resolved"])
        self.assertEqual(first["data"]["status"], "received")
        self.assertEqual(self.ticket.status, "open")

        second = tickets.create_ticket_reply(
            self.ticket.id,
            schemas.TicketReplyCreate(message="We are working on it.", status="in_progress"),
            self.admin,
            self.session,
        )
        self.assertFalse(second["data"]["is_resolved"])
        self.assertEqual(second["data"]["status"], "in_progress")
        self.assertEqual(self.ticket.status, "in_progress")

        third = tickets.create_ticket_reply(
            self.ticket.id,
            schemas.TicketReplyCreate(message="The schedule has been corrected.", status="resolved"),
            self.admin,
            self.session,
        )
        self.assertTrue(third["data"]["is_resolved"])
        self.assertEqual(third["data"]["status"], "resolved")
        self.assertEqual(self.ticket.status, "closed")

        result = tickets.get_my_tickets(self.student, self.session)
        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(
            [reply["message"] for reply in result["data"][0]["replies"]],
            ["We have received your request.", "We are working on it.", "The schedule has been corrected."],
        )
        self.assertEqual(
            [reply["responder_name"] for reply in result["data"][0]["replies"]],
            ["System Admin", "System Admin", "System Admin"],
        )
        self.assertEqual(
            [reply["admin_id"] for reply in result["data"][0]["replies"]],
            [self.admin.id, self.admin.id, self.admin.id],
        )
        self.assertEqual(
            [reply["is_resolved"] for reply in result["data"][0]["replies"]],
            [False, False, True],
        )
        self.assertEqual(
            [reply["status"] for reply in result["data"][0]["replies"]],
            ["received", "in_progress", "resolved"],
        )

    def test_legacy_resolution_payload_remains_supported(self):
        reply = tickets.create_ticket_reply(
            self.ticket.id,
            schemas.TicketReplyCreate(message="Legacy API client.", is_resolved=True),
            self.admin,
            self.session,
        )

        self.assertEqual(reply["data"]["status"], "resolved")
        self.assertTrue(reply["data"]["is_resolved"])
        self.assertEqual(self.ticket.status, "closed")

    def test_invalid_reply_status_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            tickets.create_ticket_reply(
                self.ticket.id,
                schemas.TicketReplyCreate(message="Invalid status.", status="waiting"),
                self.admin,
                self.session,
            )

        self.assertEqual(raised.exception.status_code, 422)

    def test_user_only_sees_replies_for_their_own_tickets(self):
        tickets.create_ticket_reply(
            self.ticket.id,
            schemas.TicketReplyCreate(message="Visible to the owner."),
            self.admin,
            self.session,
        )

        own_result = tickets.get_my_tickets(self.student, self.session)
        other_result = tickets.get_my_tickets(self.other_student, self.session)

        self.assertEqual([item["id"] for item in own_result["data"]], [self.ticket.id])
        self.assertEqual([item["id"] for item in other_result["data"]], [self.other_ticket.id])
        self.assertEqual(other_result["data"][0]["replies"], [])

    def test_non_admin_cannot_reply(self):
        with self.assertRaises(HTTPException) as raised:
            tickets.create_ticket_reply(
                self.ticket.id,
                schemas.TicketReplyCreate(message="Unauthorized reply."),
                self.student,
                self.session,
            )

        self.assertEqual(raised.exception.status_code, 403)

    def test_blank_reply_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            tickets.create_ticket_reply(
                self.ticket.id,
                schemas.TicketReplyCreate(message="   "),
                self.admin,
                self.session,
            )

        self.assertEqual(raised.exception.status_code, 422)

    def test_admin_ticket_list_includes_reporter_and_reply(self):
        tickets.create_ticket_reply(
            self.ticket.id,
            schemas.TicketReplyCreate(message="Admin-side visibility check."),
            self.admin,
            self.session,
        )

        result = tickets.get_tickets(self.admin, self.session)
        ticket = next(item for item in result["data"] if item["id"] == self.ticket.id)

        self.assertEqual(ticket["user_name"], "Test Student")
        self.assertEqual(ticket["replies"][0]["responder_name"], "System Admin")

    def test_replies_table_is_created_by_manual_migration(self):
        self.assertTrue(models.TicketReply.__table__.info["manual_migration"])
        self.assertIn("status", models.TicketReply.__table__.columns)


if __name__ == "__main__":
    unittest.main()
