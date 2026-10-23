import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from jose import jwt
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
from device_registry import hash_device_token  # noqa: E402
from policy import sign_policy_snapshot  # noqa: E402
from routers import agent, users  # noqa: E402


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
        self.device_token = "test-device-token"
        self.device = models.LabDevice(
            device_id="test-agent-device",
            lab_id=self.lab.id,
            device_name="Test workstation",
            device_mac="aa:bb:cc:dd:ee:ff",
            agent_token_hash=hash_device_token(self.device_token),
        )
        self.db.add(self.device)
        self.db.flush()
        self.session = models.LabAccessLog(
            user_id=self.user.id, lab_id=self.lab.id, lab_device_id=self.device.id,
            access_type="manual",
            status="success", session_status="active",
            entry_time=self.detected_at - timedelta(hours=1),
            device_mac="aa:bb:cc:dd:ee:ff",
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
            device_id=self.device.device_id, device_token=self.device_token,
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

    def test_usage_endpoint_rejects_missing_or_unbound_device_credentials(self):
        other_token = "other-device-token"
        other_device = models.LabDevice(
            device_id="other-agent-device",
            lab_id=self.lab.id,
            device_name="Other workstation",
            agent_token_hash=hash_device_token(other_token),
        )
        self.db.add(other_device)
        self.db.commit()

        for device_id, device_token in ((None, None), (other_device.device_id, other_token)):
            with self.subTest(device_id=device_id), self.assertRaises(HTTPException) as raised:
                agent.log_usage(
                    session_id=self.session.id,
                    usage_data="[]",
                    device_id=device_id,
                    device_token=device_token,
                    db=self.db,
                )
            self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.db.query(models.ProgramUsageLog).count(), 0)

    def test_bound_device_can_submit_idempotent_usage_after_session_closes(self):
        usage_data = json.dumps([{
            "event_id": "usage-event-001",
            "name": "Notepad",
            "started_at": self.detected_at.isoformat(),
            "ended_at": (self.detected_at + timedelta(minutes=1)).isoformat(),
            "duration": 60,
        }])
        self.session.session_status = "completed"
        self.session.exit_time = self.detected_at + timedelta(minutes=2)
        self.db.commit()

        first = agent.log_usage(
            session_id=self.session.id,
            usage_data=usage_data,
            device_id=self.device.device_id,
            device_token=self.device_token,
            db=self.db,
        )
        second = agent.log_usage(
            session_id=self.session.id,
            usage_data=usage_data,
            device_id=self.device.device_id,
            device_token=self.device_token,
            db=self.db,
        )

        self.assertEqual(first["created_count"], 1)
        self.assertEqual(second["duplicate_count"], 1)
        self.assertEqual(self.db.query(models.ProgramUsageLog).count(), 1)

    def test_usage_endpoint_rejects_oversized_batches_before_writing(self):
        usage_data = json.dumps([{"name": f"Program {index}"} for index in range(
            agent.MAX_USAGE_BATCH_SIZE + 1
        )])
        with self.assertRaises(HTTPException) as raised:
            agent.log_usage(
                session_id=self.session.id,
                usage_data=usage_data,
                device_id=self.device.device_id,
                device_token=self.device_token,
                db=self.db,
            )
        self.assertEqual(raised.exception.status_code, 413)
        self.assertEqual(self.db.query(models.ProgramUsageLog).count(), 0)

    def test_violation_endpoint_authenticates_before_duplicate_acknowledgment(self):
        with patch.object(agent, "apply_point_event", return_value={}) as points:
            self.deliver()
            with self.assertRaises(HTTPException) as raised:
                self.deliver(device_id=None, device_token=None)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(points.call_count, 1)
        self.assertEqual(self.db.query(models.UsageViolation).count(), 1)

    def test_end_session_requires_the_bound_device_before_mutating_session(self):
        with self.assertRaises(HTTPException) as raised:
            agent.end_session(
                session_id=self.session.id,
                end_reason="logout",
                db=self.db,
            )
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.session.session_status, "active")
        self.assertIsNone(self.session.exit_time)

    def test_legacy_session_telemetry_requires_owner_and_registered_device(self):
        self.session.lab_device_id = None
        self.db.commit()
        registered_credentials = {
            "device_id": self.device.device_id,
            "device_token": self.device_token,
        }
        denied_calls = (
            lambda: agent.log_usage(
                session_id=self.session.id,
                usage_data="[]",
                **registered_credentials,
                current_user=None,
                db=self.db,
            ),
            lambda: agent.log_violation(
                session_id=self.session.id,
                program_name="legacy.exe",
                **registered_credentials,
                current_user=None,
                db=self.db,
            ),
            lambda: agent.heartbeat(
                session_id=self.session.id,
                device_mac="aa:bb:cc:dd:ee:ff",
                **registered_credentials,
                current_user=None,
                db=self.db,
            ),
            lambda: agent.end_session(
                session_id=self.session.id,
                **registered_credentials,
                current_user=None,
                db=self.db,
            ),
        )
        for call in denied_calls:
            with self.subTest(call=call), self.assertRaises(HTTPException) as raised:
                call()
            self.assertEqual(raised.exception.status_code, 403)

        usage = agent.log_usage(
            session_id=self.session.id,
            usage_data="[]",
            **registered_credentials,
            current_user=self.user,
            db=self.db,
        )
        violation = agent.log_violation(
            session_id=self.session.id,
            program_name="legacy.exe",
            executable_identity="{}",
            detection_source="process_name",
            browser_domain=None,
            **registered_credentials,
            current_user=self.user,
            db=self.db,
        )
        heartbeat = agent.heartbeat(
            session_id=self.session.id,
            device_mac="aa:bb:cc:dd:ee:ff",
            **registered_credentials,
            current_user=self.user,
            db=self.db,
        )
        ended = agent.end_session(
            session_id=self.session.id,
            end_reason="logout",
            **registered_credentials,
            current_user=self.user,
            db=self.db,
        )

        self.assertEqual(usage["count"], 0)
        self.assertTrue(violation["ignored"])
        self.assertEqual(heartbeat["session_id"], self.session.id)
        self.assertEqual(ended["session_status"], "completed")

    def test_legacy_session_rejects_owner_with_another_device_token(self):
        self.session.lab_device_id = None
        other_device = models.LabDevice(
            device_id="another-device",
            lab_id=self.lab.id,
            device_name="Other workstation",
            device_mac="11:22:33:44:55:66",
            agent_token_hash=hash_device_token("other-token"),
        )
        self.db.add(other_device)
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            agent.log_usage(
                session_id=self.session.id,
                usage_data="[]",
                device_id=other_device.device_id,
                device_token="other-token",
                current_user=self.user,
                db=self.db,
            )

        self.assertEqual(raised.exception.status_code, 403)

    def test_optional_agent_auth_resolves_only_a_valid_user_token(self):
        token = jwt.encode(
            {"sub": self.user.email, "auth_version": self.user.auth_version},
            users.SECRET_KEY,
            algorithm=users.ALGORITHM,
        )

        resolved_user = agent._get_optional_agent_user(token, self.db)

        self.assertEqual(resolved_user.id, self.user.id)
        self.assertIsNone(agent._get_optional_agent_user("invalid-token", self.db))

    def test_bound_device_can_end_session_and_completion_points_remain_idempotent(self):
        with patch.object(agent, "apply_point_event", return_value={"change": 5}) as points:
            first = agent.end_session(
                session_id=self.session.id,
                end_reason="logout",
                device_id=self.device.device_id,
                device_token=self.device_token,
                db=self.db,
            )
            second = agent.end_session(
                session_id=self.session.id,
                end_reason="logout",
                device_id=self.device.device_id,
                device_token=self.device_token,
                db=self.db,
            )

        self.assertEqual(first["session_status"], "completed")
        self.assertEqual(second["session_status"], "completed")
        self.assertEqual(points.call_count, 1)

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

    def test_special_domains_pass_admin_policy_agent_and_violation_validation(self):
        # All writes are to this fixture's in-memory SQLite database, never production.
        from routers import blacklist
        from url_policy import normalize_domain

        for index, (entered, canonical, observed) in enumerate((
            ("https://faß.de/private?secret=1", "xn--fa-hia.de", "https://faß.de/"),
            ("ไทย.ไทย", "xn--o3cw4h.xn--o3cw4h", "https://ไทย.ไทย/"),
            ("127.1", "127.0.0.1", "http://127.0.0.1/"),
            ("https://[::ffff:192.0.2.1]:443/", "[::ffff:c000:201]", "http://[::ffff:c000:201]/"),
        )):
            with self.subTest(entered=entered):
                blacklist.create(blacklist.BlacklistCreate(
                    app_name=f"Offline domain {index}", match_type="website_domain", match_value=entered,
                ), self.user, self.db)
                row = self.db.query(models.BlacklistedApp).filter_by(app_name=f"Offline domain {index}").one()
                self.assertEqual(row.match_value, canonical)
                with patch("policy.utc_now", return_value=self.detected_at - timedelta(minutes=1)):
                    self.policy = agent.get_agent_policy(self.db)
                policy_rule = next(rule for rule in self.policy["data"] if rule["id"] == row.id)
                self.assertEqual(policy_rule["match_type"], "website_domain")
                self.assertEqual(policy_rule["match_value"], canonical)
                self.assertEqual(normalize_domain(observed), canonical)
                with patch.object(agent, "apply_point_event", return_value={}) as points:
                    payload = dict(program_name=canonical, browser_domain=canonical,
                                   event_id=f"offline-domain-{index}", detection_source="browser_domain",
                                   process_name="msedge.exe",
                                   executable_identity=json.dumps({"original_filename": "msedge.exe"}))
                    self.deliver(**payload)
                    self.deliver(**payload)
                    self.assertEqual(points.call_count, 1)
                violation = self.db.query(models.UsageViolation).filter_by(event_id=f"offline-domain-{index}").one()
                self.assertEqual(violation.program_name, canonical)
                self.assertEqual(violation.matched_rule_id, row.id)
                self.assertIsNone(violation.window_title)

    def test_unicode_domain_evidence_must_be_canonical_before_deducting_points(self):
        payload = self.website_payload()
        payload["browser_domain"] = "faß.de"
        with patch.object(agent, "apply_point_event") as points:
            with self.assertRaises(HTTPException) as raised:
                self.deliver(**payload)
            self.assertEqual(raised.exception.status_code, 422)
            points.assert_not_called()

    def test_ip_alias_evidence_must_be_canonical_before_deducting_points(self):
        payload = self.website_payload()
        payload["browser_domain"] = "127.1"
        with patch.object(agent, "apply_point_event") as points:
            with self.assertRaises(HTTPException) as raised:
                self.deliver(**payload)
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
