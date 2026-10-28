"""Cross-entry-point contract, using only synthetic data in SQLite."""

import io
import os
import sys
import unittest
from datetime import datetime, timedelta, time, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import models
import schemas
from database import Base, get_db
from device_registry import hash_device_token
from routers import agent, auth, gatekeeper, labs, password_reset, points, users
from utils import create_access_token


@compiles(JSONB, "sqlite")
def compile_jsonb(_type, _compiler, **_kwargs):
    return "TEXT"


class SharedAccessTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.now = datetime(2026, 10, 28, 2, 0, tzinfo=timezone.utc)
        self.local = self.now.replace(tzinfo=None) + timedelta(hours=7)
        self.user = models.User(email="access@example.com", password="synthetic", first_name="Access", last_name="Test", face_embedding=[1., 0., 0.])
        self.roles = {name: models.Role(name=name) for name in ("admin", "student", "guest")}
        self.lab = models.Lab(code="ACCESS", name="Access Lab", capacity=10, status="active")
        self.db.add_all([self.user, self.lab, *self.roles.values()])
        self.db.flush()
        self.user.roles = [self.roles["student"]]
        self.student = models.Student(user_id=self.user.id, student_id="ACCESS01", is_active=True)
        self.booking = models.Booking(user_id=self.user.id, lab_id=self.lab.id, booking_date=self.local.date(), start_time=time(8, 40), end_time=time(11), status="reserved")
        self.device = models.LabDevice(device_id="access-workstation", device_name="PC01", device_mac="aa:bb:cc:dd:ee:ff", lab_id=self.lab.id, status="active", agent_token_hash=hash_device_token("test-token"))
        self.camera = models.LabDevice(device_id="gatekeeper-access", device_name="Camera", lab_id=self.lab.id, status="active", agent_token_hash=hash_device_token("camera-test-token"))
        self.db.add_all([self.student, self.booking, self.device, self.camera])
        self.db.commit()
        self.app = FastAPI()
        for router in (auth.router, users.router, labs.router, agent.router, gatekeeper.router):
            self.app.include_router(router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.model = SimpleNamespace(represent=Mock(return_value=[{"embedding": [1., 0., 0.]}]))
        for patcher in (
            patch.object(agent, "utc_now", side_effect=lambda: self.now),
            patch.object(agent, "lab_now_naive", side_effect=lambda: self.local),
            patch.object(gatekeeper, "utc_now", side_effect=lambda: self.now),
            patch.object(points, "utc_now", side_effect=lambda: self.now),
            patch.object(labs, "_lab_now", side_effect=lambda: self.local),
            patch.object(gatekeeper, "get_deepface", return_value=self.model),
            patch.object(auth, "password_matches", return_value=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        _, image = cv2.imencode(".jpg", np.zeros((200, 200, 3), dtype=np.uint8))
        self.image = image.tobytes()
        self.token = create_access_token({"sub": self.user.email, "auth_version": self.user.auth_version})

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def start(self):
        return agent.start_session(email=self.user.email, device="PC01", agent_version="test", device_mac=self.device.device_mac, device_id=self.device.device_id, device_token="test-token", current_user=self.user, client_session_id="access-test-session", db=self.db)

    def scan(self):
        return self.client.post("/gatekeeper/identify", data={"device_id": self.camera.device_id, "device_token": "camera-test-token", "liveness_score": .9}, files={"face_image": ("frame.jpg", self.image, "image/jpeg")})

    def book(self):
        return labs.create_booking(schemas.BookingCreate(lab_id=self.lab.id, email=self.user.email, booking_date=self.local.date() + timedelta(days=1), slot_number=1, purpose="Test", total_participants=1), self.user, self.db)

    def login(self):
        return auth.login(SimpleNamespace(username=self.user.email, password="test-password"), self.db)

    def deny_account(self, kind):
        if kind in {"pending", "missing", "no_role"}:
            self.user.roles = [] if kind == "no_role" else [self.roles["guest"]]
            if kind == "pending":
                self.db.add(models.UserPassport(user_id=self.user.id, is_active=False))
        elif kind == "inactive":
            self.student.is_active = False
        elif kind == "ban":
            self.db.add(models.BanRecord(user_id=self.user.id, ban_until=self.now + timedelta(days=1), reason="Test"))
        self.db.commit()

    def assert_all_lab_denied(self, kind, code):
        self.deny_account(kind)
        for operation in (self.start, self.book):
            with self.assertRaises(HTTPException) as caught:
                operation()
            self.assertEqual(caught.exception.status_code, 403)
        response = self.scan()
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], code)
        self.assertEqual(self.db.query(models.GatekeeperScanLog).one().reason_code, code)
        self.assertEqual(self.db.query(models.LabAccessLog).count(), 0)
        self.assertFalse(points.get_booking_restriction(self.user.id, self.db)["booking_allowed"])
        if kind != "ban":
            with self.assertRaises(HTTPException) as caught:
                self.login()
            self.assertEqual(caught.exception.status_code, 403)
            self.assertFalse(password_reset._password_reset_eligible(self.db, self.user))

    def test_pending_guest_is_denied_everywhere(self):
        self.assert_all_lab_denied("pending", "guest_approval_required")

    def test_missing_guest_approval_fails_closed(self):
        self.assert_all_lab_denied("missing", "guest_approval_required")

    def test_roleless_account_cannot_skip_guest_approval(self):
        self.assert_all_lab_denied("no_role", "guest_approval_required")

    def test_inactive_student_is_denied_everywhere(self):
        self.assert_all_lab_denied("inactive", "account_inactive")

    def test_ban_blocks_lab_but_not_login_profile_or_recovery(self):
        self.assert_all_lab_denied("ban", "user_banned")
        self.assertTrue(self.login()["access_token"])
        self.assertTrue(password_reset._password_reset_eligible(self.db, self.user))
        response = self.client.get("/users/me", headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(response.status_code, 200, response.text)

    def test_approved_guest_keeps_booking_entry_and_session(self):
        self.user.roles = [self.roles["guest"]]
        self.db.add(models.UserPassport(user_id=self.user.id, is_active=True))
        self.db.commit()
        self.assertTrue(self.login()["access_token"])
        self.assertTrue(self.book()["booking_id"])
        self.assertEqual(self.scan().status_code, 200)
        self.assertTrue(self.start()["session_id"])

    def test_admin_role_priority_matches_profile_and_login(self):
        from jose import jwt
        self.user.roles = [self.roles["student"], self.roles["admin"]]
        self.db.commit()
        token = self.login()["access_token"]
        self.assertEqual(jwt.get_unverified_claims(token)["role"], "admin")
        self.assertEqual(users.get_my_profile(self.user, self.db)["role"], "admin")
        self.db.delete(self.booking)
        self.db.commit()
        with self.assertRaises(HTTPException):
            self.start()
        self.assertEqual(self.scan().json()["detail"]["code"], "booking_required")

    def test_ban_expiration_is_exclusive_on_every_surface(self):
        self.db.add(models.BanRecord(user_id=self.user.id, ban_until=self.now, reason="Expired"))
        self.db.commit()
        self.assertTrue(self.book()["booking_id"])
        self.assertEqual(self.scan().status_code, 200)
        self.assertTrue(self.start()["session_id"])

    def test_recovery_and_gatekeeper_deny_exact_end_of_booking(self):
        session_id = self.start()["session_id"]
        self.assertTrue(self.start()["recovered"])
        self.assertEqual(self.scan().status_code, 200)
        self.local = self.local.replace(hour=11)
        self.now = self.now.replace(hour=4)
        with self.assertRaises(HTTPException) as caught:
            self.start()
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(self.scan().json()["detail"]["code"], "booking_required")
        self.assertEqual(self.db.query(models.LabAccessLog).count(), 1)

    def test_existing_token_cannot_bypass_withdrawn_approval(self):
        self.deny_account("pending")
        response = self.client.post("/agent/start-session", headers={"Authorization": f"Bearer {self.token}"}, data={"email": self.user.email, "device": "PC01", "device_mac": self.device.device_mac, "device_id": self.device.device_id, "device_token": "test-token"})
        self.assertEqual(response.status_code, 403, response.text)
        response = self.client.post("/bookings", headers={"Authorization": f"Bearer {self.token}"}, json={"lab_id": self.lab.id, "email": self.user.email, "booking_date": str(self.local.date() + timedelta(days=1)), "slot_number": 1, "purpose": "Test", "total_participants": 1})
        self.assertEqual(response.status_code, 403, response.text)

    def test_heartbeat_revocation_preserves_telemetry_and_has_no_completion_bonus(self):
        session_id = self.start()["session_id"]
        credentials = {"device_id": self.device.device_id, "device_token": "test-token", "current_user": None, "db": self.db}
        self.assertEqual(agent.heartbeat(session_id, device_mac=self.device.device_mac, **credentials)["session_id"], session_id)
        self.deny_account("ban")
        with self.assertRaises(HTTPException) as caught:
            agent.heartbeat(session_id, device_mac=self.device.device_mac, **credentials)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.get(models.LabAccessLog, session_id).end_reason, "access_revoked")
        result = agent.end_session(session_id, end_reason="logout", **credentials)
        self.assertIsNone(result["points"])
        import json
        result = agent.log_usage(session_id, json.dumps([{"name": "notepad.exe", "duration": 1, "event_id": "revoked-session-final-usage"}]), **credentials)
        self.assertEqual(self.db.query(models.ProgramUsageLog).count(), 1)

    def test_normal_booking_expiry_keeps_one_completion_event(self):
        session_id = self.start()["session_id"]
        self.local = self.local.replace(hour=11)
        self.now = self.now.replace(hour=4)
        credentials = {"device_id": self.device.device_id, "device_token": "test-token", "current_user": None, "db": self.db}
        with self.assertRaises(HTTPException) as caught:
            agent.heartbeat(session_id, device_mac=self.device.device_mac, **credentials)
        self.assertEqual(caught.exception.status_code, 409)
        agent.end_session(session_id, end_reason="logout", **credentials)
        self.assertEqual(self.db.query(models.PointLog).filter_by(reason="complete_session").count(), 1)
        self.assertEqual(self.db.get(models.LabAccessLog, session_id).end_reason, "logout")

    def test_commit_race_cannot_recover_session_for_another_booking(self):
        # Simulate another request winning the unique client-session key after
        # the initial reads. Recovery must repeat the booking authorization.
        user_id, lab_id, device_id = self.user.id, self.lab.id, self.device.id
        original_commit = self.db.commit
        def concurrent_commit():
            self.db.rollback()
            other = models.Booking(user_id=user_id, lab_id=lab_id,
                booking_date=self.local.date() + timedelta(days=1),
                start_time=time(8, 40), end_time=time(11), status="attended")
            self.db.add(other)
            self.db.flush()
            self.db.add(models.LabAccessLog(user_id=user_id, lab_id=lab_id, lab_device_id=device_id,
                booking_id=other.id, entry_time=self.now, last_heartbeat_at=self.now,
                access_type="manual", status="success", session_status="active",
                device_mac="aa:bb:cc:dd:ee:ff", client_session_id="access-test-session"))
            original_commit()
            raise IntegrityError("synthetic conflict", {}, Exception("duplicate key"))
        with (
            patch.object(agent, "mark_due_no_shows", return_value=0),
            patch.object(agent, "_cleanup_stale_sessions", return_value=0),
            patch.object(self.db, "commit", side_effect=concurrent_commit),
            self.assertRaises(HTTPException) as caught,
        ):
            self.start()
        self.assertEqual(caught.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
