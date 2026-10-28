import os
import sys
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import models  # noqa: E402
from database import Base, get_db  # noqa: E402
from device_registry import hash_device_token  # noqa: E402
from routers import gatekeeper, points, users  # noqa: E402
from face_service import gatekeeper_inference_slot  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb(_type, _compiler, **_kwargs):
    return "TEXT"


class GatekeeperAccessTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.now = datetime(2026, 10, 28, 2, 0, tzinfo=timezone.utc)  # 09:00 Bangkok
        self.lab = models.Lab(name="Camera Lab", code="CAM01", capacity=10, status="active")
        self.other_lab = models.Lab(name="Other Lab", code="CAM02", capacity=10, status="active")
        self.user = models.User(
            first_name="Scan", last_name="Student", email="scan@example.invalid",
            password="unused", face_embedding=[1.0, 0.0, 0.0],
        )
        self.admin = models.User(
            first_name="Scan", last_name="Admin", email="admin@example.invalid", password="unused",
        )
        self.student_role = models.Role(name="student")
        self.guest_role = models.Role(name="guest")
        self.admin_role = models.Role(name="admin")
        self.db.add_all([
            self.lab, self.other_lab, self.user, self.admin,
            self.student_role, self.guest_role, self.admin_role,
        ])
        self.db.flush()
        self.user.roles = [self.student_role]
        self.admin.roles = [self.admin_role]
        self.student = models.Student(user_id=self.user.id, student_id="TEST01", is_active=True)
        self.device = models.LabDevice(
            device_id="gatekeeper-access-test", lab_id=self.lab.id, device_name="Test Camera",
            status="active", agent_token_hash=hash_device_token("synthetic-camera-token"),
        )
        self.booking = models.Booking(
            user_id=self.user.id, lab_id=self.lab.id, booking_date=date(2026, 10, 28),
            start_time=time(9, 0), end_time=time(10, 0), status="reserved",
        )
        self.db.add_all([self.student, self.device, self.booking])
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(gatekeeper.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)
        self.model = SimpleNamespace(represent=Mock(return_value=[{"embedding": [1.0, 0.0, 0.0]}]))
        self.patches = [
            patch.object(gatekeeper, "get_deepface", return_value=self.model),
            patch.object(gatekeeper, "utc_now", side_effect=lambda: self.now),
            patch.object(points, "utc_now", side_effect=lambda: self.now),
        ]
        for patcher in self.patches:
            patcher.start()
        ok, image = cv2.imencode(".jpg", np.zeros((200, 200, 3), dtype=np.uint8))
        self.assertTrue(ok)
        self.image = image.tobytes()

    def tearDown(self):
        self.client.close()
        for patcher in reversed(self.patches):
            patcher.stop()
        self.db.close()
        self.engine.dispose()

    def identify(self, *, image=True, **changes):
        data = {
            "device_id": self.device.device_id,
            "device_token": "synthetic-camera-token",
            "lab_code": "CLIENT-LAB-IGNORED",
            "liveness_score": "0.90",
            "liveness_passed": "true",
        }
        data.update(changes)
        files = {"face_image": ("frame.jpg", self.image, "image/jpeg")} if image else None
        return self.client.post("/gatekeeper/identify", data=data, files=files)

    def scans(self):
        return self.db.query(models.GatekeeperScanLog).order_by(models.GatekeeperScanLog.id).all()

    def assert_denied(self, response, code, status=403):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(response.json()["detail"]["code"], code)
        row = self.scans()[-1]
        self.assertEqual(response.json()["detail"]["scan_id"], row.id)
        self.assertEqual(row.decision, "denied")
        self.assertEqual(row.reason_code, code)
        return row

    def make_guest(self, approved=None):
        self.user.roles = [self.guest_role]
        if approved is not None:
            self.db.add(models.UserPassport(user_id=self.user.id, phone="0812345678", is_active=approved))
        self.db.commit()

    def test_grant_is_audited_and_does_not_consume_the_agents_booking(self):
        response = self.identify()
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIs(payload["access_granted"], True)
        self.assertEqual(payload["booking_id"], self.booking.id)
        row = self.scans()[0]
        self.assertEqual((row.lab_id, row.user_id, row.booking_id), (
            self.lab.id, self.user.id, self.booking.id,
        ))
        self.assertEqual(row.device_id, self.device.device_id)
        self.assertEqual(row.lab_code, self.lab.code)
        self.assertEqual(row.reason_code, "access_granted")
        self.assertEqual(payload["scan_id"], row.id)
        self.assertEqual(row.scanned_at.replace(tzinfo=timezone.utc), self.now)
        self.db.refresh(self.booking)
        self.assertEqual(self.booking.status, "reserved")
        self.assertIsNone(self.booking.checked_in_at)
        self.assertEqual(self.db.query(models.LabAccessLog).count(), 0)
        self.assertEqual(self.db.query(models.PointLog).count(), 0)

    def test_attended_booking_allows_reentry_without_creating_an_agent_session(self):
        self.booking.status = "attended"
        self.db.commit()
        self.assertEqual(self.identify().status_code, 200)
        self.assertEqual(self.db.query(models.LabAccessLog).count(), 0)

    def test_missing_or_closed_booking_statuses_are_rejected(self):
        for booking_status in ("cancelled", "completed", "no_show"):
            with self.subTest(status=booking_status):
                self.booking.status = booking_status
                self.db.commit()
                self.assert_denied(self.identify(), "booking_required")
        self.db.delete(self.booking)
        self.db.commit()
        self.assert_denied(self.identify(), "booking_required")

    def test_inactive_lab_denial_is_audited_before_running_face_inference(self):
        self.lab.status = "maintenance"
        self.db.commit()
        row = self.assert_denied(self.identify(), "lab_unavailable")
        self.assertEqual(row.lab_id, self.lab.id)
        self.model.represent.assert_not_called()

    def test_booking_must_belong_to_the_recognized_user_and_registered_lab(self):
        self.booking.lab_id = self.other_lab.id
        self.db.commit()
        row = self.assert_denied(self.identify(lab_code=self.other_lab.code), "booking_required")
        self.assertEqual(row.lab_id, self.lab.id)
        self.booking.lab_id = self.lab.id
        self.booking.user_id = self.admin.id
        self.db.commit()
        self.assert_denied(self.identify(), "booking_required")

    def test_booking_time_includes_start_but_excludes_end_and_other_dates(self):
        self.assertEqual(self.identify().status_code, 200)
        for instant in (
            self.now - timedelta(seconds=1),
            self.now + timedelta(hours=1),
            self.now + timedelta(days=1),
        ):
            with self.subTest(instant=instant):
                self.now = instant
                self.assert_denied(self.identify(), "booking_required")

    def test_booking_calendar_uses_bangkok_date_after_utc_midnight_boundary(self):
        self.now = datetime(2026, 10, 27, 17, 30, tzinfo=timezone.utc)
        self.booking.start_time, self.booking.end_time = time(0, 0), time(1, 0)
        self.db.commit()
        self.assertEqual(self.identify().status_code, 200)

    def test_booking_is_rechecked_after_face_inference(self):
        def finish_after_booking_ends(**_kwargs):
            self.now += timedelta(hours=1)
            return [{"embedding": [1.0, 0.0, 0.0]}]
        self.model.represent.side_effect = finish_after_booking_ends
        self.assert_denied(self.identify(), "booking_required")

    def test_face_inference_does_not_hold_a_database_connection_or_transaction(self):
        held = {"count": 0}
        event.listen(self.engine, "checkout", lambda *_args: held.update(count=held["count"] + 1))
        event.listen(self.engine, "checkin", lambda *_args: held.update(count=held["count"] - 1))
        def inference(**_kwargs):
            self.assertEqual(held["count"], 0)
            self.assertFalse(self.db.in_transaction())
            return [{"embedding": [1.0, 0.0, 0.0]}]
        self.model.represent.side_effect = inference
        self.assertEqual(self.identify().status_code, 200)
        self.assertEqual(len(self.scans()), 1)

    def test_busy_inference_is_denied_and_audited_without_running_another_model(self):
        with gatekeeper_inference_slot():
            response = self.identify()
        self.assert_denied(response, "face_service_busy", status=503)
        self.model.represent.assert_not_called()
        self.assertEqual(self.identify().status_code, 200)

    def test_model_exception_releases_inference_slot_for_next_scan(self):
        self.model.represent.side_effect = RuntimeError("synthetic")
        self.assert_denied(self.identify(), "face_service_unavailable", status=503)
        self.model.represent.side_effect = None
        self.assertEqual(self.identify().status_code, 200)

    def test_account_ban_and_booking_changes_during_inference_are_not_cached(self):
        user_id, booking_id = self.user.id, self.booking.id
        mutations = (
            (lambda db: db.query(models.Student).filter_by(user_id=user_id).update({"is_active": False}),
             "account_inactive"),
            (lambda db: db.add(models.BanRecord(user_id=user_id, ban_until=self.now + timedelta(days=1))),
             "user_banned"),
            (lambda db: db.query(models.Booking).filter_by(id=booking_id).update({"status": "cancelled"}),
             "booking_required"),
        )
        for mutate, reason in mutations:
            with self.subTest(reason=reason):
                self.db.query(models.Student).filter_by(user_id=user_id).update({"is_active": True})
                self.db.query(models.BanRecord).delete()
                self.db.commit()
                def inference(**_kwargs):
                    with Session(self.engine) as other:
                        mutate(other)
                        other.commit()
                    return [{"embedding": [1.0, 0.0, 0.0]}]
                self.model.represent.side_effect = inference
                self.assert_denied(self.identify(), reason)

    def test_guest_approval_withdrawn_during_inference_is_denied(self):
        self.make_guest(approved=True)
        user_id = self.user.id
        def inference(**_kwargs):
            with Session(self.engine) as other:
                other.query(models.UserPassport).filter_by(user_id=user_id).update({"is_active": False})
                other.commit()
            return [{"embedding": [1.0, 0.0, 0.0]}]
        self.model.represent.side_effect = inference
        self.assert_denied(self.identify(), "guest_approval_required")

    def test_lab_becoming_inactive_or_reassigned_during_inference_cannot_grant(self):
        lab_id, other_id, device_id = self.lab.id, self.other_lab.id, self.device.device_id
        def inactive(**_kwargs):
            with Session(self.engine) as other:
                other.query(models.Lab).filter_by(id=lab_id).update({"status": "maintenance"})
                other.commit()
            return [{"embedding": [1.0, 0.0, 0.0]}]
        self.model.represent.side_effect = inactive
        self.assert_denied(self.identify(), "lab_unavailable")
        self.db.query(models.Lab).filter_by(id=lab_id).update({"status": "active"})
        self.db.commit()
        def reassign(**_kwargs):
            with Session(self.engine) as other:
                other.query(models.LabDevice).filter_by(device_id=device_id).update({"lab_id": other_id})
                other.commit()
            return [{"embedding": [1.0, 0.0, 0.0]}]
        self.model.represent.side_effect = reassign
        row = self.assert_denied(self.identify(), "lab_unavailable")
        self.assertEqual(row.lab_id, other_id)

    def test_device_revoked_during_inference_cannot_grant(self):
        device_id = self.device.device_id
        def inference(**_kwargs):
            with Session(self.engine) as other:
                other.query(models.LabDevice).filter_by(device_id=device_id).update({"status": "revoked"})
                other.commit()
            return [{"embedding": [1.0, 0.0, 0.0]}]
        self.model.represent.side_effect = inference
        response = self.identify()
        self.assert_denied(response, "camera_unavailable")
        self.assertNotIn("access_granted", response.json())

    def test_pending_guest_is_denied_even_with_a_valid_booking(self):
        self.make_guest(approved=False)
        row = self.assert_denied(self.identify(), "guest_approval_required")
        self.assertEqual(row.user_id, self.user.id)

    def test_guest_with_missing_approval_record_is_denied(self):
        self.make_guest()
        self.assert_denied(self.identify(), "guest_approval_required")

    def test_extra_role_or_missing_role_does_not_bypass_guest_approval(self):
        self.user.roles = [self.guest_role, self.student_role]
        self.db.commit()
        self.assert_denied(self.identify(), "guest_approval_required")
        self.user.roles = []
        self.db.commit()
        self.assert_denied(self.identify(), "guest_approval_required")

    def test_approved_guest_with_booking_is_allowed(self):
        self.make_guest(approved=True)
        self.assertEqual(self.identify().status_code, 200)

    def test_inactive_student_is_denied(self):
        self.student.is_active = False
        self.db.commit()
        self.assert_denied(self.identify(), "account_inactive")

    def test_active_ban_blocks_entry_even_when_booking_exists(self):
        self.db.add(models.BanRecord(user_id=self.user.id, ban_until=self.now + timedelta(days=1)))
        self.db.commit()
        self.assert_denied(self.identify(), "user_banned")

    def test_expired_ban_and_low_points_do_not_create_a_new_access_restriction(self):
        self.db.add_all([
            models.BanRecord(user_id=self.user.id, ban_until=self.now - timedelta(seconds=1)),
            models.UserPoints(user_id=self.user.id, points=0),
        ])
        self.db.commit()
        self.assertEqual(self.identify().status_code, 200)
        self.assertEqual(self.db.query(models.PointLog).count(), 0)

    def test_unknown_face_has_an_anonymous_denied_audit_record(self):
        self.model.represent.return_value = [{"embedding": [0.0, 1.0, 0.0]}]
        row = self.assert_denied(self.identify(), "face_not_recognized")
        self.assertIsNone(row.user_id)
        self.assertIsNone(row.booking_id)

    def test_low_liveness_and_local_motion_rejection_are_logged_without_an_image(self):
        self.assert_denied(self.identify(image=False, liveness_score="0.10"), "liveness_failed")
        self.assert_denied(self.identify(
            image=False, liveness_score="0.95", liveness_passed="false", liveness_reason="no_motion",
        ), "liveness_no_motion")
        self.model.represent.assert_not_called()

    def test_capture_failure_reasons_are_distinct_and_never_reach_face_matching(self):
        for reason, code in (
            ("insufficient_samples", "liveness_insufficient_samples"),
            ("multiple_faces", "exactly_one_face_required"),
            ("face_changed", "liveness_face_changed"),
            ("untrusted-reason", "liveness_failed"),
        ):
            with self.subTest(reason=reason):
                self.assert_denied(self.identify(
                    image=False, liveness_score="0.95", liveness_passed="false", liveness_reason=reason,
                ), code)
        self.model.represent.assert_not_called()

    def test_scan_and_enrollment_use_identical_face_options_and_small_face_guard(self):
        from face_service import FACE_REPRESENT_OPTIONS
        self.assertEqual(self.identify().status_code, 200)
        options = self.model.represent.call_args.kwargs
        self.assertEqual({key: options[key] for key in FACE_REPRESENT_OPTIONS}, FACE_REPRESENT_OPTIONS)
        self.model.represent.return_value = [{
            "embedding": [1, 0, 0], "facial_area": {"w": 20, "h": 20},
        }]
        self.assert_denied(self.identify(), "face_too_small", status=400)

    def test_zero_faces_are_not_reported_as_multiple_people(self):
        self.model.represent.return_value = []
        self.assert_denied(self.identify(), "face_not_detected", status=400)
        self.assertTrue(all(row.user_id is None for row in self.scans()))

    def test_invalid_image_and_multiple_faces_are_audited(self):
        self.image = b"invalid-image"
        self.assert_denied(self.identify(), "invalid_face_image", status=400)
        self.model.represent.assert_not_called()
        ok, image = cv2.imencode(".jpg", np.zeros((20, 20, 3), dtype=np.uint8))
        self.assertTrue(ok)
        self.image = image.tobytes()
        self.model.represent.return_value = [{"embedding": [1, 0, 0]}, {"embedding": [0, 1, 0]}]
        self.assert_denied(self.identify(), "exactly_one_face_required", status=400)

    def test_model_failure_is_denied_and_logged_without_exposing_exception_details(self):
        self.model.represent.side_effect = RuntimeError("private model path")
        response = self.identify()
        self.assert_denied(response, "face_service_unavailable", status=503)
        self.assertNotIn("private model path", response.text)

    def test_invalid_liveness_values_are_audited_without_storing_invalid_numbers(self):
        for value in ("1.1", "-0.1", "NaN"):
            with self.subTest(value=value):
                row = self.assert_denied(self.identify(liveness_score=value), "invalid_liveness_score", status=422)
                self.assertIsNone(row.liveness_score)
        self.model.represent.assert_not_called()

    def test_invalid_threshold_configuration_falls_back_to_safe_defaults(self):
        self.model.represent.return_value = [{"embedding": [0.0, 1.0, 0.0]}]
        with patch.dict(os.environ, {"FACE_MATCH_MAX_COSINE_DISTANCE": "NaN"}):
            self.assert_denied(self.identify(), "face_not_recognized")
        with patch.dict(os.environ, {"GATEKEEPER_LIVENESS_THRESHOLD": "-1"}):
            self.assert_denied(self.identify(image=False, liveness_score="0.10"), "liveness_failed")

    def test_invalid_camera_does_not_run_inference_or_pollute_scan_history(self):
        self.assertEqual(self.identify(device_token="wrong").status_code, 403)
        self.model.represent.assert_not_called()
        self.assertEqual(self.scans(), [])

    def test_history_storage_failure_prevents_a_grant_and_does_not_change_booking(self):
        models.GatekeeperScanLog.__table__.drop(self.engine)
        response = self.identify()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "scan_history_unavailable")
        self.assertNotIn("access_granted", response.json())
        self.db.refresh(self.booking)
        self.assertEqual(self.booking.status, "reserved")

    def test_legacy_scan_cannot_bypass_access_checks_or_create_a_session(self):
        response = self.client.post("/gatekeeper/scan", json={
            "email": self.user.email, "lab_id": self.lab.id, "score": 1.0, "is_real": True,
        })
        self.assertEqual(response.status_code, 410)
        self.assertEqual(self.db.query(models.LabAccessLog).count(), 0)
        self.assertEqual(self.scans(), [])

    def test_history_is_admin_only_and_has_cursor_pagination_and_filters(self):
        self.assertEqual(self.client.get("/admin/gatekeeper/scans").status_code, 401)
        self.app.dependency_overrides[users.get_current_user] = lambda: self.user
        self.assertEqual(self.client.get("/admin/gatekeeper/scans").status_code, 403)
        self.app.dependency_overrides[users.get_current_user] = lambda: self.admin
        self.identify()
        self.identify()
        self.booking.status = "cancelled"
        self.db.commit()
        self.identify()
        first = self.client.get("/admin/gatekeeper/scans", params={"limit": 2}).json()
        second = self.client.get("/admin/gatekeeper/scans", params={
            "limit": 2, "before_id": first["next_before_id"],
        }).json()
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        ids = [row["id"] for row in first["data"] + second["data"]]
        self.assertEqual(ids, [row.id for row in reversed(self.scans())])
        filtered = self.client.get("/admin/gatekeeper/scans", params={
            "decision": "denied", "lab_id": self.lab.id, "user_id": self.user.id,
            "device_id": self.device.device_id,
        }).json()["data"]
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["reason_code"], "booking_required")
        for private_field in ("face_image", "face_embedding", "device_token"):
            self.assertNotIn(private_field, str(first))

    def test_scan_table_requires_operator_migration_in_production(self):
        self.assertTrue(models.GatekeeperScanLog.__table__.info["manual_migration"])


if __name__ == "__main__":
    unittest.main()
