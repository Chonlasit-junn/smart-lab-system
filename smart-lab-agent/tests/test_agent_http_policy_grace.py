import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests


AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Import the Agent module without reading a computer's saved registration token.
import agent_device  # noqa: E402

_load_device_registration = agent_device.load_device_registration
agent_device.load_device_registration = lambda: {}
_loader = importlib.machinery.SourceFileLoader(
    "smart_lab_agent_runtime_test",
    str(AGENT_DIR / "agent.pyw"),
)
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
agent = importlib.util.module_from_spec(_spec)
_loader.exec_module(agent)
agent_device.load_device_registration = _load_device_registration


def make_response(status_code, payload):
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(payload).encode("utf-8")
    response.headers["Content-Type"] = "application/json"
    return response


class AgentHttpTests(unittest.TestCase):
    def test_heartbeat_preserves_http_conflict_status(self):
        instance = SimpleNamespace(flush_outbox=Mock())
        conflict = make_response(409, {"detail": "Session is no longer active."})

        with patch.object(agent, "post_with_retry", return_value=conflict):
            result = agent.SmartLabAgent._send_heartbeat_request(instance, 12)

        self.assertEqual(result["status"], 409)
        instance.flush_outbox.assert_not_called()

    def test_closed_session_request_retries_with_a_fresh_key(self):
        overlay = agent.LoginOverlay.__new__(agent.LoginOverlay)
        overlay.agent = SimpleNamespace(
            flush_outbox=Mock(),
            get_or_create_session_attempt=Mock(
                side_effect=["client-key-1", "client-key-2"]
            ),
            discard_session_attempt=Mock(),
            confirm_session_attempt=Mock(),
        )
        responses = [
            make_response(200, {"access_token": "test-token"}),
            make_response(409, {"detail": "Session request is already closed."}),
            make_response(200, {"session_id": 42}),
        ]

        with patch.object(agent, "post_with_retry", side_effect=responses) as post:
            result = agent.LoginOverlay._authenticate_and_start_session(
                overlay,
                "student@example.invalid",
                "test-password",
            )

        self.assertEqual(
            result,
            {"kind": "success", "session_id": 42, "email": "student@example.invalid"},
        )
        self.assertEqual(post.call_count, 3)
        overlay.agent.discard_session_attempt.assert_called_once_with("client-key-1")
        overlay.agent.confirm_session_attempt.assert_called_once_with("client-key-2")

    def test_failed_start_session_keeps_the_http_status(self):
        overlay = agent.LoginOverlay.__new__(agent.LoginOverlay)
        overlay.agent = SimpleNamespace(
            flush_outbox=Mock(),
            get_or_create_session_attempt=Mock(return_value="client-key"),
            discard_session_attempt=Mock(),
            confirm_session_attempt=Mock(),
        )
        responses = [
            make_response(200, {"access_token": "test-token"}),
            make_response(422, {"detail": "Invalid session data."}),
        ]

        with patch.object(agent, "post_with_retry", side_effect=responses):
            result = agent.LoginOverlay._authenticate_and_start_session(
                overlay,
                "student@example.invalid",
                "test-password",
            )

        self.assertEqual(result, {"kind": "session_error", "status": 422})


class AgentOutboxRetryTests(unittest.TestCase):
    def test_outbox_retry_runs_through_background_task_runner(self):
        background_tasks = Mock()
        instance = SimpleNamespace(
            outbox=object(),
            background_tasks=background_tasks,
            flush_outbox=Mock(return_value=2),
            _handle_outbox_retry=Mock(),
        )

        submitted = agent.SmartLabAgent.retry_outbox(instance)

        self.assertTrue(submitted)
        args, kwargs = background_tasks.submit.call_args
        self.assertEqual(args[0], "outbox-retry")
        self.assertEqual(args[1](), 2)
        self.assertIs(args[2], instance._handle_outbox_retry)
        self.assertEqual(kwargs, {})

    def test_outbox_retry_is_skipped_when_persistence_is_unavailable(self):
        background_tasks = Mock()
        instance = SimpleNamespace(outbox=None, background_tasks=background_tasks)

        submitted = agent.SmartLabAgent.retry_outbox(instance)

        self.assertFalse(submitted)
        background_tasks.submit.assert_not_called()

    def test_activity_is_not_kept_in_memory_after_durable_enqueue(self):
        ended_at = agent._utc_now().replace(microsecond=0)
        started_at = ended_at - timedelta(seconds=3)
        instance = SimpleNamespace(
            current_activity_name="Editor",
            current_activity_started_at=started_at,
            current_session_id=12,
            usage_segments=[],
            _queue_outbox=Mock(return_value=True),
        )

        agent.SmartLabAgent._close_current_activity(instance, ended_at)

        self.assertEqual(instance.usage_segments, [])
        instance._queue_outbox.assert_called_once()

    def test_activity_is_kept_in_memory_when_durable_enqueue_fails(self):
        ended_at = agent._utc_now().replace(microsecond=0)
        started_at = ended_at - timedelta(seconds=3)
        instance = SimpleNamespace(
            current_activity_name="Editor",
            current_activity_started_at=started_at,
            current_session_id=12,
            usage_segments=[],
            _queue_outbox=Mock(return_value=False),
        )

        agent.SmartLabAgent._close_current_activity(instance, ended_at)

        self.assertEqual(len(instance.usage_segments), 1)
        self.assertEqual(instance.usage_segments[0]["name"], "Editor")


class AgentPolicyTests(unittest.TestCase):
    @staticmethod
    def make_agent():
        return SimpleNamespace(
            policy_rules=[],
            policy_version=None,
            policy_source=None,
            seen_process_ids=set(),
        )

    def test_empty_policy_clears_cached_rules(self):
        instance = self.make_agent()
        self.assertTrue(
            agent.SmartLabAgent._set_policy(
                instance,
                [
                    {
                        "id": 1,
                        "app_name": "Blocked App",
                        "match_type": "process_name",
                        "match_value": "blocked",
                        "enabled": True,
                    }
                ],
                "version-1",
                "cache",
            )
        )
        instance.seen_process_ids.add(123)

        self.assertTrue(
            agent.SmartLabAgent._set_policy(instance, [], "version-2", "backend")
        )

        self.assertEqual(instance.policy_rules, [])
        self.assertEqual(instance.policy_version, "version-2")
        self.assertEqual(instance.policy_source, "backend")
        self.assertEqual(instance.seen_process_ids, set())

    def test_empty_backend_policy_is_valid_and_cached(self):
        instance = SimpleNamespace(outbox=Mock())
        response = make_response(200, {"version": "empty-policy", "data": []})

        with patch.object(agent.requests, "get", return_value=response):
            result = agent.SmartLabAgent._request_policy(instance)

        self.assertEqual(result, {"rules": [], "version": "empty-policy"})
        instance.outbox.save_policy_cache.assert_called_once()

    def test_empty_cached_policy_does_not_enable_fallback(self):
        instance = agent.SmartLabAgent.__new__(agent.SmartLabAgent)
        instance.info_bar = None
        instance.usage_segments = []
        instance.current_activity_name = None
        instance.current_activity_started_at = None
        instance.current_session_id = 12
        instance.policy_rules = []
        instance.policy_version = None
        instance.policy_source = None
        instance.seen_process_ids = set()
        instance.violation_reported = False
        instance.violation_state = agent.ViolationState()
        instance.violation_dialog_active = False
        instance.session_cleanup = None
        instance.monitor_timer = Mock()
        instance.heartbeat_timer = Mock()
        instance.policy_timer = Mock()
        instance.fetch_policy = Mock()
        instance._use_fallback_policy = Mock()

        def load_empty_cache():
            instance.policy_version = "empty-policy"
            instance.policy_source = "cache"
            return True

        instance._load_cached_policy = Mock(side_effect=load_empty_cache)

        with patch.object(agent, "SESSION_CLEANUP_ENABLED", False):
            agent.SmartLabAgent.start_monitoring(instance, 12, None)

        instance._use_fallback_policy.assert_not_called()
        instance.fetch_policy.assert_called_once()

    def test_empty_cached_policy_is_kept_when_refresh_fails(self):
        instance = self.make_agent()
        instance.policy_source = "cache"
        instance._use_fallback_policy = Mock()

        agent.SmartLabAgent._handle_policy_result(
            instance,
            None,
            RuntimeError("offline"),
        )

        instance._use_fallback_policy.assert_not_called()

    def test_invalid_refresh_does_not_replace_empty_cache_with_fallback(self):
        instance = self.make_agent()
        instance.policy_source = "cache"
        instance._use_fallback_policy = Mock()
        instance._set_policy = lambda rules, version, source: agent.SmartLabAgent._set_policy(
            instance,
            rules,
            version,
            source,
        )

        agent.SmartLabAgent._handle_policy_result(
            instance,
            {"rules": [{"invalid": True}], "version": "invalid"},
            None,
        )

        self.assertEqual(instance.policy_source, "cache")
        self.assertEqual(instance.policy_rules, [])
        instance._use_fallback_policy.assert_not_called()

    def test_empty_backend_policy_is_applied_without_fallback(self):
        instance = self.make_agent()
        instance._use_fallback_policy = Mock()
        instance._set_policy = lambda rules, version, source: agent.SmartLabAgent._set_policy(
            instance,
            rules,
            version,
            source,
        )

        agent.SmartLabAgent._handle_policy_result(
            instance,
            {"rules": [], "version": "empty-policy"},
            None,
        )

        self.assertEqual(instance.policy_rules, [])
        self.assertEqual(instance.policy_source, "backend")
        instance._use_fallback_policy.assert_not_called()


class AgentGracePeriodTests(unittest.TestCase):
    def test_grace_period_keeps_tracking_usage_but_skips_violation_checks(self):
        instance = agent.SmartLabAgent.__new__(agent.SmartLabAgent)
        instance.current_session_id = 12
        instance.violation_dialog_active = False
        instance.violation_state = SimpleNamespace(
            clear_expired_grace=Mock(return_value=False),
            is_grace_active=Mock(return_value=True),
        )
        instance.policy_rules = [
            {
                "id": 1,
                "app_name": "Blocked App",
                "match_type": "window_title",
                "match_value": "blocked",
                "enabled": True,
            }
        ]
        instance.seen_process_ids = set()
        instance.current_activity_name = None
        instance.current_activity_started_at = None
        instance.usage_segments = []
        instance._find_new_process_match = Mock(return_value=None)
        instance._handle_violation_detection = Mock()
        active_window = SimpleNamespace(title="Blocked App")

        with patch.object(agent.gw, "getActiveWindow", return_value=active_window):
            agent.SmartLabAgent.track_usage(instance)

        instance._find_new_process_match.assert_not_called()
        instance._handle_violation_detection.assert_not_called()
        self.assertEqual(instance.current_activity_name, "Blocked App")
        self.assertIsNotNone(instance.current_activity_started_at)

    def test_violation_detection_resumes_after_grace_expires(self):
        instance = agent.SmartLabAgent.__new__(agent.SmartLabAgent)
        instance.current_session_id = 12
        instance.current_activity_name = None
        instance.current_activity_started_at = None
        instance.violation_dialog_active = False
        instance.violation_state = SimpleNamespace(
            clear_expired_grace=Mock(return_value=True),
            is_grace_active=Mock(return_value=False),
        )
        matched_rule = {"app_name": "Blocked App", "match_value": "blocked"}
        instance._find_new_process_match = Mock(
            return_value=("blocked.exe", r"C:\\blocked.exe", matched_rule, "executable_identity",
                          {"original_filename": "blocked.exe"})
        )
        instance._handle_violation_detection = Mock()
        instance.seen_process_ids = {123}

        with patch.object(agent.gw, "getActiveWindow") as get_active_window:
            agent.SmartLabAgent.track_usage(instance)

        self.assertEqual(instance.seen_process_ids, set())
        instance._handle_violation_detection.assert_called_once()
        context = instance._handle_violation_detection.call_args.args[0]
        self.assertEqual(context["process_name"], "blocked.exe")
        get_active_window.assert_not_called()


class AgentTelemetryTests(unittest.TestCase):
    def make_agent(self):
        instance = agent.SmartLabAgent.__new__(agent.SmartLabAgent)
        instance.current_session_id = 12
        instance.current_activity_name = None
        instance.current_activity_started_at = None
        instance.usage_segments = []
        instance._queue_outbox = Mock(return_value=True)
        instance.policy_rules = [{
            "id": 1, "app_name": "Blocked", "match_type": "process_name",
            "match_value": "blocked", "enabled": True,
        }]
        instance.policy_version = "original-version"
        instance.policy_token = "original-receipt"
        instance.seen_process_ids = {123}
        instance.violation_state = agent.ViolationState()
        instance.violation_reported = False
        instance.violation_dialog_active = False
        instance.monitor_timer = Mock()
        instance._finalize_violation = Mock()
        return instance

    def warning_context(self, instance):
        return {
            "program_name": "blocked.exe", "reason": "Forbidden app",
            "process_name": "blocked.exe", "detection_source": "process_name",
            "matched_rule": instance.policy_rules[0],
        }

    def test_closed_app_after_warning_resumes_monitor_without_logout(self):
        instance = self.make_agent()
        instance._violation_is_still_present = Mock(return_value=False)
        dialog = Mock()
        dialog.exec.return_value = agent.QDialog.DialogCode.Rejected
        with patch.object(agent, "ViolationDialog", return_value=dialog):
            instance._handle_violation_detection(self.warning_context(instance))
        instance._finalize_violation.assert_not_called()
        instance.monitor_timer.start.assert_called_once_with(5000)
        self.assertEqual(instance.seen_process_ids, set())
        self.assertEqual(instance.violation_state.attempts, 1)

    def test_open_app_after_warning_uses_original_timestamp_and_policy(self):
        instance = self.make_agent()
        instance._violation_is_still_present = Mock(return_value=True)
        detected_at = agent._utc_now()
        dialog = Mock()

        def timeout():
            instance.policy_version = "new-version"
            instance.policy_token = "new-receipt"
            return agent.QDialog.DialogCode.Rejected

        dialog.exec.side_effect = timeout
        with patch.object(agent, "ViolationDialog", return_value=dialog), patch.object(
            agent, "_utc_now", return_value=detected_at,
        ):
            instance._handle_violation_detection(self.warning_context(instance))
        context = instance._finalize_violation.call_args.args[0]
        self.assertEqual(context["detected_at"], detected_at.isoformat(timespec="seconds"))
        self.assertEqual(context["policy_version"], "original-version")
        self.assertEqual(context["policy_token"], "original-receipt")

    def test_window_only_evidence_cannot_continue_a_warning(self):
        instance = self.make_agent()
        rule = {"match_type": "window_title", "match_value": "blocked"}
        context = {"detection_source": "window_title", "matched_rule": rule}
        with patch.object(agent.gw, "getAllWindows", return_value=[
            SimpleNamespace(title="Warning"), SimpleNamespace(title="Blocked App"),
        ]):
            self.assertFalse(instance._violation_is_still_present(context))
        with patch.object(agent.gw, "getAllWindows", return_value=[SimpleNamespace(title="Editor")]):
            self.assertFalse(instance._violation_is_still_present(context))

    def test_process_recheck_does_not_skip_a_previously_seen_process(self):
        instance = self.make_agent()
        process = SimpleNamespace(info={"pid": 123, "name": "blocked.exe"},
                                  exe=Mock(return_value=r"C:\blocked.exe"))
        with patch.object(agent.psutil, "process_iter", return_value=[process]), patch.object(
            agent, "read_executable_identity", return_value={"original_filename": "blocked.exe"},
        ):
            self.assertTrue(instance._violation_is_still_present(self.warning_context(instance)))
        with patch.object(agent.psutil, "process_iter", return_value=[]):
            self.assertFalse(instance._violation_is_still_present(self.warning_context(instance)))

    def test_new_process_detection_uses_embedded_identity_not_observed_filename(self):
        for observed, original, expected in (
            ("blocked.exe", "notepad.exe", False),
            ("notes.exe", "blocked.exe", True),
        ):
            with self.subTest(observed=observed):
                instance = self.make_agent()
                instance.seen_process_ids.clear()
                process = SimpleNamespace(info={"pid": 123, "name": observed},
                                          exe=Mock(return_value=r"C:\apps\program.exe"))
                with patch.object(agent.psutil, "process_iter", return_value=[process]), patch.object(
                    agent, "read_executable_identity", return_value={"original_filename": original},
                ):
                    result = instance._find_new_process_match()
                self.assertEqual(result is not None, expected)
                if result:
                    self.assertEqual(result[4]["original_filename"], original)

    def test_inaccessible_process_name_alone_cannot_continue_warning(self):
        instance = self.make_agent()
        process = SimpleNamespace(info={"pid": 123, "name": "blocked.exe"},
                                  exe=Mock(side_effect=agent.psutil.AccessDenied(123)))
        with patch.object(agent.psutil, "process_iter", return_value=[process]):
            self.assertFalse(instance._violation_is_still_present(self.warning_context(instance)))

    def test_closed_or_unreadable_website_does_not_end_session(self):
        instance = self.make_agent()
        instance.browser_url_monitor = Mock()
        rule = {"match_type": "website_domain", "match_value": "example.com"}
        context = {"detection_source": "browser_domain", "matched_rule": rule}
        for observation in (None, {"domain": "allowed.example"}):
            instance.browser_url_monitor.recheck.return_value = observation
            self.assertFalse(instance._violation_is_still_present(context))
        instance.browser_url_monitor.recheck.return_value = {"domain": "sub.example.com"}
        self.assertTrue(instance._violation_is_still_present(context))

    def test_website_detection_enters_the_existing_warning_flow(self):
        instance = self.make_agent()
        instance.policy_rules = [{"match_type": "website_domain", "match_value": "example.com"}]
        instance._find_new_process_match = Mock(return_value=None)
        instance._handle_violation_detection = Mock()
        instance.browser_url_monitor = Mock()
        instance.browser_url_monitor.poll.return_value = {
            "domain": "example.com", "hwnd": 42, "pid": 123,
            "process_name": "msedge.exe", "exe_path": r"C:\msedge.exe",
            "executable_identity": {"original_filename": "msedge.exe"},
        }
        instance.track_usage()
        context = instance._handle_violation_detection.call_args.args[0]
        self.assertEqual(context["browser_domain"], "example.com")
        self.assertEqual(context["detection_source"], "browser_domain")

    def test_periodic_checkpoints_and_logout_do_not_overlap(self):
        instance = self.make_agent()
        started_at = agent._utc_now().replace(microsecond=0)
        instance._track_active_activity("Editor", started_at)
        instance._checkpoint_current_activity(started_at + timedelta(seconds=29))
        instance._queue_outbox.assert_not_called()
        instance._checkpoint_current_activity(started_at + timedelta(seconds=30))
        instance._checkpoint_current_activity(started_at + timedelta(seconds=60))
        instance._close_current_activity(started_at + timedelta(seconds=65))
        segments = [json.loads(call.kwargs["payload"]["usage_data"])[0]
                    for call in instance._queue_outbox.call_args_list]
        self.assertEqual([segment["duration"] for segment in segments], [30, 30, 5])
        self.assertEqual(segments[0]["ended_at"], segments[1]["started_at"])
        self.assertEqual(segments[1]["ended_at"], segments[2]["started_at"])
        self.assertEqual(len({segment["event_id"] for segment in segments}), 3)
        self.assertEqual(instance.usage_segments, [])

    def test_signed_policy_receipt_is_persisted_and_restored_from_cache(self):
        instance = self.make_agent()
        instance.outbox = Mock()
        response = make_response(200, {
            "version": "signed-version", "data": instance.policy_rules,
            "policy_token": "signed-receipt",
        })
        with patch.object(agent.requests, "get", return_value=response):
            result = instance._request_policy()
        instance._handle_policy_result(result, None)
        self.assertEqual(instance.policy_token, "signed-receipt")
        cached = instance.outbox.save_policy_cache.call_args.args[1]
        instance.outbox.load_policy_cache.return_value = cached
        instance.policy_token = None
        self.assertTrue(instance._load_cached_policy())
        self.assertEqual(instance.policy_token, "signed-receipt")

    def test_checkpoint_survives_reopening_the_sqlite_outbox(self):
        instance = self.make_agent()
        started_at = agent._utc_now().replace(microsecond=0)
        with tempfile.TemporaryDirectory() as temporary:
            path = str(Path(temporary) / "outbox.sqlite3")
            instance.outbox = agent.AgentOutbox(path)
            # Use the real durable queue rather than the UI-only test mock.
            del instance._queue_outbox
            instance._track_active_activity("Editor", started_at)
            instance._checkpoint_current_activity(started_at + timedelta(seconds=30))
            restored = agent.AgentOutbox(path)
            pending = restored.pending()
            self.assertEqual(len(pending), 1)
            segment = json.loads(json.loads(pending[0]["payload"])["usage_data"])[0]
            self.assertEqual(segment["duration"], 30)
            self.assertEqual(segment["name"], "Editor")

    def test_monitor_tick_checkpoints_an_unchanged_foreground_app(self):
        instance = self.make_agent()
        started_at = agent._utc_now().replace(microsecond=0)
        instance._track_active_activity("Editor", started_at)
        instance._find_new_process_match = Mock(return_value=None)
        with patch.object(agent, "_utc_now", return_value=started_at + timedelta(seconds=30)), patch.object(
            agent.gw, "getActiveWindow", return_value=SimpleNamespace(title="Editor"),
        ):
            instance.track_usage()
        instance._queue_outbox.assert_called_once()
        self.assertEqual(instance.current_activity_name, "Editor")

    def test_agent_owned_window_is_not_recorded_as_an_application(self):
        instance = self.make_agent()
        instance.violation_state = SimpleNamespace(
            clear_expired_grace=Mock(return_value=False),
            is_grace_active=Mock(return_value=True),
        )
        with patch.object(agent, "_is_agent_window", return_value=True), patch.object(
            agent.gw, "getActiveWindow", return_value=SimpleNamespace(title="Smart Lab Access"),
        ):
            instance.track_usage()

        self.assertIsNone(instance.current_activity_name)
        instance._queue_outbox.assert_not_called()

    def test_agent_process_is_not_matched_as_a_forbidden_application(self):
        instance = self.make_agent()
        process = SimpleNamespace(info={"pid": 123, "name": "SmartLabAgent.exe"})
        with patch.object(agent.os, "getpid", return_value=123), patch.object(
            agent.psutil, "process_iter", return_value=[process],
        ), patch.object(agent, "read_executable_identity") as read_identity:
            result = instance._find_new_process_match()

        self.assertIsNone(result)
        read_identity.assert_not_called()

    def test_agent_window_detection_uses_owning_process_id(self):
        process_id = 4321

        def get_window_process_id(_handle, output):
            output._obj.value = process_id

        user32 = SimpleNamespace(GetWindowThreadProcessId=get_window_process_id)
        with patch.object(agent.ctypes, "windll", SimpleNamespace(user32=user32), create=True), patch.object(
            agent.os, "getpid", return_value=process_id,
        ):
            self.assertTrue(agent._is_agent_window(SimpleNamespace(_hWnd=99)))
            self.assertFalse(agent._is_agent_window(SimpleNamespace(_hWnd=0)))

    def test_violation_metadata_is_saved_in_the_durable_payload(self):
        instance = self.make_agent()
        instance.report_violation(
            "blocked.exe", "Forbidden", detected_at="2026-10-22T10:00:00+00:00",
            policy_version="original-version", policy_token="original-receipt",
        )
        payload = instance._queue_outbox.call_args.kwargs["payload"]
        self.assertEqual(payload["detected_at"], "2026-10-22T10:00:00+00:00")
        self.assertEqual(payload["policy_token"], "original-receipt")


if __name__ == "__main__":
    unittest.main()
