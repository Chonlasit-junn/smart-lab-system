import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import models  # noqa: E402
from database import Base  # noqa: E402
from policy import sign_policy_snapshot  # noqa: E402
from routers import agent  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


@compiles(BigInteger, "sqlite")
def compile_bigint_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class AgentTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.received_at = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
        self.detected_at = self.received_at - timedelta(hours=2)
        self.user = models.User(
            first_name="Test", last_name="Student",
            email="student@example.test", password="hashed",
        )
        self.lab = models.Lab(name="Lab", code="LAB1", capacity=20, status="active")
        self.db.add_all([self.user, self.lab])
        self.db.flush()
        self.session = models.LabAccessLog(
            user_id=self.user.id, lab_id=self.lab.id, access_type="manual",
            status="success", session_status="active",
            entry_time=self.detected_at - timedelta(hours=1),
        )
        self.rule = models.BlacklistedApp(
            app_name="Blocked", match_type="process_name", match_value="blocked", enabled=True,
        )
        self.db.add_all([self.session, self.rule])
        self.db.commit()
        with patch("policy.utc_now", return_value=self.detected_at - timedelta(minutes=1)):
            self.policy = agent.get_agent_policy(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def deliver(self, **changes):
        payload = dict(
            session_id=self.session.id, program_name="blocked.exe", reason="Forbidden",
            action_taken="logout", event_id="event-001", process_name="blocked.exe",
            exe_path=None, window_title=None, detection_source="process_name",
            detected_at=self.detected_at.isoformat(), policy_version=self.policy["version"],
            policy_token=self.policy["policy_token"], db=self.db,
            executable_identity=json.dumps({"original_filename": "blocked.exe"}),
            browser_domain=None,
        )
        payload.update(changes)
        with patch.object(agent, "utc_now", return_value=self.received_at):
            return agent.log_violation(**payload)

    def test_delayed_event_survives_rule_deletion_and_session_closure(self):
        rule_id = self.rule.id
        self.db.delete(self.rule)
        self.session.session_status = "completed"
        self.session.exit_time = self.detected_at + timedelta(minutes=1)
        self.db.commit()
        with patch.object(agent, "apply_point_event", return_value={"change": -10}) as points:
            self.deliver()
            self.deliver()
        row = self.db.query(models.UsageViolation).one()
        self.assertEqual(row.detected_at.replace(tzinfo=timezone.utc), self.detected_at)
        self.assertEqual(row.policy_version, self.policy["version"])
        self.assertEqual(row.matched_rule_id, rule_id)
        self.assertEqual(points.call_count, 1)
        self.assertEqual(points.call_args.kwargs["effective_at"], self.detected_at)

    def test_changed_rule_uses_the_signed_original_matching_value(self):
        self.rule.match_value = "another-app"
        self.db.commit()
        with patch.object(agent, "apply_point_event", return_value={}):
            self.deliver()
        self.assertEqual(self.db.query(models.UsageViolation).count(), 1)

    def test_tampered_receipt_cannot_create_a_violation_or_points(self):
        prefix, signature = self.policy["policy_token"].rsplit(".", 1)
        token = prefix + "." + ("a" if signature[0] != "a" else "b") + signature[1:]
        with patch.object(agent, "apply_point_event") as points:
            with self.assertRaises(HTTPException) as raised:
                self.deliver(policy_token=token)
        self.assertEqual(raised.exception.status_code, 422)
        points.assert_not_called()
        self.assertEqual(self.db.query(models.UsageViolation).count(), 0)

    def test_valid_receipt_still_requires_matching_evidence(self):
        with self.assertRaises(HTTPException) as raised:
            self.deliver(program_name="editor.exe", process_name="editor.exe",
                         executable_identity=json.dumps({"original_filename": "editor.exe"}))
        self.assertEqual(raised.exception.status_code, 422)

    def test_mismatched_version_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            self.deliver(policy_version="forged-version")
        self.assertEqual(raised.exception.status_code, 422)

    def test_receipt_issued_after_the_detection_is_rejected(self):
        with patch("policy.utc_now", return_value=self.detected_at + timedelta(minutes=10)):
            token = sign_policy_snapshot(self.policy)
        with self.assertRaises(HTTPException) as raised:
            self.deliver(policy_token=token)
        self.assertEqual(raised.exception.status_code, 422)

    def test_invalid_or_out_of_session_timestamps_are_rejected(self):
        for timestamp in (
            "bad-date", (self.received_at + timedelta(hours=1)).isoformat(),
            (self.detected_at - timedelta(hours=2)).isoformat(),
        ):
            with self.subTest(timestamp=timestamp), self.assertRaises(HTTPException) as raised:
                self.deliver(detected_at=timestamp)
            self.assertEqual(raised.exception.status_code, 422)

    def test_legacy_payload_is_acknowledged_without_penalty(self):
        with patch.object(agent, "apply_point_event") as points:
            result = self.deliver(detected_at=None, policy_token=None, policy_version=None,
                                  executable_identity=None)
        self.assertTrue(result["ignored"])
        points.assert_not_called()
        self.assertEqual(self.db.query(models.UsageViolation).count(), 0)

    def test_renamed_editor_cannot_be_penalized_by_observed_name_or_title(self):
        with patch.object(agent, "apply_point_event") as points:
            with self.assertRaises(HTTPException) as raised:
                self.deliver(process_name="blocked.exe", window_title="Blocked Game",
                             executable_identity=json.dumps({"original_filename": "notepad.exe"}))
        self.assertEqual(raised.exception.status_code, 422)
        points.assert_not_called()

    def test_renamed_forbidden_executable_still_matches_its_identity(self):
        with patch.object(agent, "apply_point_event", return_value={}):
            self.deliver(process_name="notes.exe", window_title="Notes")
        self.assertEqual(self.db.query(models.UsageViolation).count(), 1)

    def test_malformed_identity_is_rejected(self):
        for identity in ("[]", "bad-json", '{"original_filename": 1}', "x" * 4097):
            with self.subTest(identity=identity[:30]), self.assertRaises(HTTPException) as raised:
                self.deliver(executable_identity=identity)
            self.assertEqual(raised.exception.status_code, 422)

    def website_payload(self):
        self.rule.match_type = "website_domain"
        self.rule.match_value = "example.com"
        self.db.commit()
        with patch("policy.utc_now", return_value=self.detected_at - timedelta(minutes=1)):
            self.policy = agent.get_agent_policy(self.db)
        return dict(program_name="example.com", browser_domain="example.com",
                    detection_source="browser_domain", process_name="msedge.exe",
                    executable_identity=json.dumps({"original_filename": "msedge.exe"}))

    def test_browser_domain_uses_existing_idempotent_point_delivery(self):
        payload = self.website_payload()
        self.db.delete(self.rule)
        self.db.commit()
        with patch.object(agent, "apply_point_event", return_value={}) as points:
            self.deliver(**payload)
            self.deliver(**payload)
        self.assertEqual(points.call_count, 1)
        row = self.db.query(models.UsageViolation).one()
        self.assertEqual(row.program_name, "example.com")
        self.assertEqual(row.detection_source, "browser_domain")
        self.assertIsNone(row.window_title)

    def test_browser_domain_requires_browser_identity_and_canonical_domain(self):
        payload = self.website_payload()
        for changes in (
            {"browser_domain": "https://example.com/private?secret=1"},
            {"browser_domain": "example.com.evil.com"},
            {"browser_domain": None},
            {"executable_identity": json.dumps({"original_filename": "notepad.exe"})},
        ):
            with self.subTest(changes=changes), patch.object(agent, "apply_point_event") as points:
                with self.assertRaises(HTTPException) as raised:
                    self.deliver(**(payload | changes))
                self.assertEqual(raised.exception.status_code, 422)
                points.assert_not_called()

    def test_point_failure_rolls_back_the_violation_for_a_later_retry(self):
        with patch.object(agent, "apply_point_event", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(HTTPException) as raised:
                self.deliver()
        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(self.db.query(models.UsageViolation).count(), 0)
        with patch.object(agent, "apply_point_event", return_value={}):
            self.deliver()
        self.assertEqual(self.db.query(models.UsageViolation).count(), 1)

    def test_unsigned_historical_policy_cannot_bypass_current_rules(self):
        self.db.delete(self.rule)
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            self.deliver(policy_token=None)
        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
