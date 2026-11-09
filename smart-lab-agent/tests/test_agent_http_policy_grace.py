import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
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
    def test_login_throttle_and_inactive_account_do_not_attempt_session_start(self):
        for status, detail, kind in (
            (429, "Too many login attempts. Please try again later.", "login_limited"),
            (403, "This account is not active.", "account_inactive"),
            (403, "Your account is pending admin approval.", "approval_required"),
            (503, "Service unavailable", "connection_error"),
        ):
            overlay = agent.LoginOverlay.__new__(agent.LoginOverlay)
            overlay.agent = SimpleNamespace(flush_outbox=Mock())
            with patch.object(agent, "post_with_retry", return_value=make_response(status, {"detail": detail})) as post:
                result = agent.LoginOverlay._authenticate_and_start_session(overlay, "test@example.com", "password")
            self.assertEqual(result["kind"], kind)
            self.assertEqual(post.call_count, 1)
            overlay.agent.flush_outbox.assert_not_called()

    def test_ban_after_login_is_explained_and_session_not_confirmed(self):
        overlay = agent.LoginOverlay.__new__(agent.LoginOverlay)
        overlay.agent = SimpleNamespace(flush_outbox=Mock(), get_or_create_session_attempt=Mock(return_value="key"), confirm_session_attempt=Mock())
        with patch.object(agent, "post_with_retry", side_effect=[
            make_response(200, {"access_token": "test-token"}),
            make_response(403, {"detail": "This account has an active ban."}),
        ]):
            result = agent.LoginOverlay._authenticate_and_start_session(overlay, "test@example.com", "password")
        self.assertEqual(result, {"kind": "user_banned"})
        overlay.agent.confirm_session_attempt.assert_not_called()
        overlay.login_btn = SimpleNamespace(setText=Mock(), setEnabled=Mock())
        overlay._show_error = Mock()
        agent.LoginOverlay._handle_login_result(overlay, result, None)
        self.assertIn("ระงับ", overlay._show_error.call_args.args[0])

    def test_revoked_device_heartbeat_returns_to_login(self):
        instance = SimpleNamespace(current_session_id=7, heartbeat_timer=SimpleNamespace(stop=Mock()), info_bar=SimpleNamespace(trigger_logout=Mock()))
        agent.SmartLabAgent._handle_heartbeat_result(instance, 7, {"status": 403}, None)
        instance.heartbeat_timer.stop.assert_called_once()
        instance.info_bar.trigger_logout.assert_called_once()

    def test_heartbeat_preserves_http_conflict_status(self):
        instance = SimpleNamespace(
            flush_outbox=Mock(),
            current_access_token="legacy-owner-token",
        )
        conflict = make_response(409, {"detail": "Session is no longer active."})

        with patch.object(agent, "post_with_retry", return_value=conflict) as post:
            result = agent.SmartLabAgent._send_heartbeat_request(instance, 12)

        self.assertEqual(result["status"], 409)
        instance.flush_outbox.assert_not_called()
        self.assertEqual(
            post.call_args.kwargs["headers"],
            {"Authorization": "Bearer legacy-owner-token"},
        )

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
        self.assertEqual(
            post.call_args_list[1].kwargs["headers"],
            {"Authorization": "Bearer test-token"},
        )
        self.assertEqual(
            post.call_args_list[2].kwargs["headers"],
            {"Authorization": "Bearer test-token"},
        )
        self.assertEqual(overlay.agent.current_access_token, "test-token")
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

    def test_booking_required_response_is_explained_to_agent_user(self):
        overlay = agent.LoginOverlay.__new__(agent.LoginOverlay)
        overlay.agent = SimpleNamespace(
            flush_outbox=Mock(),
            get_or_create_session_attempt=Mock(return_value="client-key"),
            discard_session_attempt=Mock(),
            confirm_session_attempt=Mock(),
        )
        with patch.object(agent, "post_with_retry", side_effect=[
            make_response(200, {"access_token": "test-token"}),
            make_response(403, {
                "detail": "An active Lab booking is required to start an Agent session.",
            }),
        ]):
            result = agent.LoginOverlay._authenticate_and_start_session(
                overlay,
                "student@example.invalid",
                "test-password",
            )

        self.assertEqual(result, {"kind": "booking_required"})

        overlay.login_btn = SimpleNamespace(setText=Mock(), setEnabled=Mock())
        overlay._show_error = Mock()
        agent.LoginOverlay._handle_login_result(overlay, result, None)
        overlay._show_error.assert_called_once()
        self.assertIn("จอง Lab", overlay._show_error.call_args.args[0])

    def test_login_response_without_access_token_does_not_start_a_session(self):
        overlay = agent.LoginOverlay.__new__(agent.LoginOverlay)
        overlay.agent = SimpleNamespace(
            flush_outbox=Mock(),
            get_or_create_session_attempt=Mock(),
            discard_session_attempt=Mock(),
            confirm_session_attempt=Mock(),
        )

        with patch.object(
            agent,
            "post_with_retry",
            return_value=make_response(200, {}),
        ) as post:
            result = agent.LoginOverlay._authenticate_and_start_session(
                overlay,
                "student@example.invalid",
                "test-password",
            )

        self.assertEqual(result, {"kind": "invalid_credentials"})
        self.assertEqual(post.call_count, 1)
        overlay.agent.get_or_create_session_attempt.assert_not_called()

    def test_outbox_delivery_attaches_current_registered_device_credentials(self):
        outbox = SimpleNamespace(
            pending=Mock(return_value=[{
                "kind": "usage",
                "payload": json.dumps({"session_id": 42, "usage_data": "[]"}),
                "event_id": "usage-event",
            }]),
            mark_sent=Mock(),
            mark_failed=Mock(),
        )
        instance = SimpleNamespace(
            outbox=outbox,
            current_access_token="legacy-owner-token",
        )

        with patch.object(agent, "REGISTERED_DEVICE_ID", "device-1"), patch.object(
            agent, "DEVICE_TOKEN", "device-secret",
        ), patch.object(agent, "post_with_retry", return_value=make_response(200, {})) as post:
            sent = agent.SmartLabAgent._flush_outbox_locked(instance)

        self.assertEqual(sent, 1)
        request_data = post.call_args.kwargs["data"]
        self.assertEqual(request_data["device_id"], "device-1")
        self.assertEqual(request_data["device_token"], "device-secret")
        self.assertEqual(
            post.call_args.kwargs["headers"],
            {"Authorization": "Bearer legacy-owner-token"},
        )
        outbox.mark_sent.assert_called_once_with("usage-event")

    def test_fallback_usage_summary_is_sent_in_bounded_batches(self):
        instance = SimpleNamespace(
            current_access_token="agent-token",
            _send_fallback_violation_logs=Mock(),
        )
        summary = [{"name": f"Program {index}", "event_id": f"usage-{index}"}
                   for index in range(205)]

        with patch.object(agent, "post_with_retry", return_value=make_response(200, {})) as post:
            agent.SmartLabAgent._send_fallback_session_logs(
                instance, 42, summary, "logout", [],
            )

        usage_calls = [call for call in post.call_args_list
                       if call.args[0].endswith("/agent/log-usage")]
        sent_batches = [json.loads(call.kwargs["data"]["usage_data"]) for call in usage_calls]
        self.assertEqual([len(batch) for batch in sent_batches], [100, 100, 5])
        self.assertEqual(
            [item["event_id"] for batch in sent_batches for item in batch],
            [item["event_id"] for item in summary],
        )


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
            seen_visible_process_ids=set(),
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
        instance.seen_visible_process_ids = set()
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

        with patch.object(agent, "SESSION_CLEANUP_ENABLED", False), patch.object(
            agent.SmartLabAgent, "_start_window_visibility_monitor",
        ):
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
            clear_grace=Mock(return_value=True),
        )
        instance.violation_grace_context = {"program_name": "Blocked App"}
        instance._violation_is_still_present = Mock(return_value=True)
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
        instance.seen_visible_process_ids = set()
        instance.current_activity_name = None
        instance.current_activity_started_at = None
        instance.usage_segments = []
        instance._find_new_process_match = Mock(return_value=None)
        instance._handle_violation_detection = Mock()
        active_window = SimpleNamespace(title="Blocked App")

        with patch.object(agent.gw, "getActiveWindow", return_value=active_window), patch.object(
            agent, "_usage_name_for_window", return_value="blocked.exe",
        ):
            agent.SmartLabAgent.track_usage(instance)

        instance._find_new_process_match.assert_not_called()
        instance._handle_violation_detection.assert_not_called()
        self.assertEqual(instance.current_activity_name, "blocked.exe")
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
        instance.violation_grace_context = {"program_name": "Blocked App"}
        matched_rule = {"app_name": "Blocked App", "match_value": "blocked"}
        instance._find_new_process_match = Mock(
            return_value=("blocked.exe", r"C:\\blocked.exe", matched_rule, "executable_identity",
                          {"original_filename": "blocked.exe"}, 123, False)
        )
        instance._handle_violation_detection = Mock()
        instance.seen_process_ids = {123}
        instance.seen_visible_process_ids = set()

        with patch.object(agent.gw, "getActiveWindow") as get_active_window:
            agent.SmartLabAgent.track_usage(instance)

        self.assertEqual(instance.seen_process_ids, set())
        self.assertIsNone(instance.violation_grace_context)
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
        instance.seen_visible_process_ids = set()
        instance.violation_state = agent.ViolationState()
        instance.violation_grace_context = None
        instance.violation_reported = False
        instance.violation_dialog_active = False
        instance.monitor_timer = Mock()
        instance._finalize_violation = Mock()
        return instance

    @contextmanager
    def foreground_process(
        self, *, exe_path=r"C:\Windows\notepad.exe", identity=None,
        process_name="notepad.exe", window_class="Notepad",
    ):
        window = SimpleNamespace(_hWnd=99, title="StarRail - Notepad")
        process = Mock(spec=["exe", "name"])
        process.exe.return_value = exe_path
        process.name.return_value = process_name
        if identity is None:
            identity = {"original_filename": "NOTEPAD.EXE"}
        with patch.object(agent.gw, "getActiveWindow", return_value=window), patch.object(
            agent, "_window_process_id", return_value=os.getpid() + 1,
        ), patch.object(agent.psutil, "Process", return_value=process), patch.object(
            agent, "read_executable_identity", return_value=identity,
        ), patch.object(agent, "_window_class_name", return_value=window_class):
            yield window, process

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
        self.assertEqual(instance.seen_process_ids, {123})
        self.assertEqual(instance.violation_state.attempts, 1)

    def test_closing_app_during_grace_ends_chance_and_reopened_app_is_detected(self):
        instance = self.make_agent()
        now = agent.datetime.now()
        instance.violation_state.register_detection(now)
        instance.violation_state.grant_grace(now)
        instance.violation_grace_context = self.warning_context(instance)
        instance.violation_grace_context["process_id"] = 123
        process = SimpleNamespace(info={"pid": 456, "name": "blocked.exe"},
                                  exe=Mock(return_value=r"C:\blocked.exe"))
        process_iter = Mock(return_value=[process])
        read_identity = Mock(return_value={"original_filename": "blocked.exe"})
        instance.seen_process_ids = {123}
        dialog = Mock()
        dialog.exec.return_value = agent.QDialog.DialogCode.Accepted

        with patch.object(agent, "ViolationDialog", return_value=dialog), patch.object(
            agent.psutil, "process_iter", process_iter,
        ), patch.object(agent, "read_executable_identity", read_identity), patch.object(
            agent.gw, "getActiveWindow",
        ) as get_active_window:
            agent.SmartLabAgent.track_usage(instance)

        self.assertEqual(instance.violation_state.attempts, 2)
        self.assertEqual(instance.violation_grace_context.get("process_id"), 456)
        self.assertTrue(instance.violation_state.is_grace_active(agent.datetime.now()))
        self.assertEqual(process_iter.call_count, 2)
        self.assertEqual(read_identity.call_count, 1)
        dialog.exec.assert_called_once()
        get_active_window.assert_not_called()

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
                    agent, "_visible_window_handles_by_pid", return_value={},
                ), patch.object(
                    agent, "read_executable_identity", return_value={"original_filename": original},
                ):
                    result = instance._find_new_process_match()
                self.assertEqual(result is not None, expected)
                if result:
                    self.assertEqual(result[4]["original_filename"], original)

    def test_same_process_is_detected_again_when_its_window_reopens(self):
        instance = self.make_agent()
        instance.seen_process_ids.clear()
        process = SimpleNamespace(
            info={"pid": 123, "name": "blocked.exe"},
            exe=Mock(return_value=r"C:\blocked.exe"),
        )
        with patch.object(agent.psutil, "process_iter", return_value=[process]), patch.object(
            agent, "_visible_window_handles_by_pid", return_value={},
        ), patch.object(
            agent, "read_executable_identity", return_value={"original_filename": "blocked.exe"},
        ):
            first_open = instance._find_new_process_match()
            closed_but_resident = instance._find_new_process_match()

        self.assertIsNotNone(first_open)
        self.assertIsNone(closed_but_resident)

        with patch.object(agent.psutil, "process_iter", return_value=[process]), patch.object(
            agent, "_visible_window_handles_by_pid", return_value={123: {100}},
        ), patch.object(
            agent, "read_executable_identity", return_value={"original_filename": "blocked.exe"},
        ):
            reopened = instance._find_new_process_match()
            same_open_episode = instance._find_new_process_match()

        self.assertIsNotNone(reopened)
        self.assertTrue(reopened[6])
        self.assertIsNone(same_open_episode)

    def test_polling_fallback_detects_recreated_window_with_other_window_still_visible(self):
        instance = self.make_agent()
        instance.seen_process_ids = {123}
        instance.seen_visible_process_ids = {123}
        instance.seen_visible_window_handles_by_pid = {123: {100, 101}}
        instance.pending_window_reopen_process_ids = set()
        instance.window_visibility_monitor = None
        process = SimpleNamespace(
            info={"pid": 123, "name": "blocked.exe"},
            exe=Mock(return_value=r"C:\blocked.exe"),
        )

        with patch.object(agent.psutil, "process_iter", return_value=[process]), patch.object(
            agent, "_visible_window_handles_by_pid", side_effect=[
                {123: {101}},
                {123: {101, 200}},
            ],
        ), patch.object(
            agent, "read_executable_identity", return_value={"original_filename": "blocked.exe"},
        ):
            closed_window = instance._find_new_process_match()
            reopened_window = instance._find_new_process_match()

        self.assertIsNone(closed_window)
        self.assertIsNotNone(reopened_window)
        self.assertEqual(reopened_window[5], 123)

    def test_window_event_catches_reopen_between_ticks_during_grace(self):
        instance = self.make_agent()
        instance.seen_process_ids = {123}
        instance.seen_visible_process_ids = {123}
        now = agent.datetime.now()
        instance.violation_state.register_detection(now)
        instance.violation_state.grant_grace(now)
        instance.violation_grace_context = {
            **self.warning_context(instance),
            "process_id": 123,
            "process_window_visible": True,
        }
        instance._violation_is_still_present = Mock(return_value=True)
        instance._handle_violation_detection = Mock()
        monitor = Mock()
        monitor.consume_shown_process_ids.return_value = {123}
        instance.window_visibility_monitor = monitor
        process = SimpleNamespace(
            info={"pid": 123, "name": "blocked.exe"},
            exe=Mock(return_value=r"C:\blocked.exe"),
        )

        with patch.object(agent.psutil, "process_iter", return_value=[process]), patch.object(
            agent, "_visible_window_handles_by_pid", return_value={123: {100}},
        ), patch.object(
            agent, "read_executable_identity", return_value={"original_filename": "blocked.exe"},
        ):
            agent.SmartLabAgent.track_usage(instance)

        instance._violation_is_still_present.assert_not_called()
        instance._handle_violation_detection.assert_called_once()
        context = instance._handle_violation_detection.call_args.args[0]
        self.assertEqual(context["process_id"], 123)
        monitor.prune.assert_called_once_with({123})

    def test_visible_process_warning_ends_when_its_window_closes(self):
        instance = self.make_agent()
        process = SimpleNamespace(
            info={"pid": 123, "name": "blocked.exe"},
            exe=Mock(return_value=r"C:\blocked.exe"),
        )
        context = {
            **self.warning_context(instance),
            "process_id": 123,
            "process_window_visible": True,
        }
        with patch.object(agent, "_visible_window_process_ids", return_value=set()), patch.object(
            agent.psutil, "process_iter", return_value=[process],
        ):
            self.assertFalse(instance._violation_is_still_present(context))

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

    def test_violation_enqueue_failure_uses_fallback_even_with_an_outbox(self):
        instance = agent.SmartLabAgent.__new__(agent.SmartLabAgent)
        instance.stop_browser_monitor = Mock()
        instance.monitor_timer = Mock()
        instance.heartbeat_timer = Mock()
        instance.policy_timer = Mock()
        instance._close_current_activity = Mock()
        instance.usage_segments = []
        instance.outbox = Mock()
        instance.outbox.has_pending_for_session.return_value = False
        instance._pending_fallback_violations = [{
            "session_id": 12,
            "event_id": "violation-retry",
            "program_name": "blocked.exe",
        }]
        instance._queue_outbox = Mock(side_effect=[False, True])
        instance.flush_outbox = Mock()
        instance.background_tasks = Mock()
        instance._cleanup_session = Mock()
        instance.current_access_token = "test-token"
        instance.current_session_id = 12
        instance.current_activity_name = None
        instance.current_activity_started_at = None
        instance.policy_rules = []
        instance.policy_version = None
        instance.policy_source = None
        instance.policy_token = None
        instance.seen_process_ids = set()
        instance.seen_visible_process_ids = set()
        instance.violation_state = agent.ViolationState()
        instance.violation_grace_context = None
        instance.violation_dialog_active = False
        call_order = []

        with patch.object(agent, "DEBUG_MODE", False), patch.object(
            agent.os, "system", side_effect=lambda _command: call_order.append("logout"),
        ) as logoff:
            agent.SmartLabAgent.stop_and_send_logs(instance, 12, "violation")
            logoff.assert_not_called()
        deliver = instance.background_tasks.submit.call_args.args[1]
        handle_delivery = instance.background_tasks.submit.call_args.args[2]

        def record_post(url, **_kwargs):
            call_order.append("violation" if url.endswith("/agent/log-violation") else "other")
            return make_response(200, {})

        instance.flush_outbox.side_effect = lambda **_kwargs: call_order.append("outbox")
        with patch.object(agent, "post_with_retry", side_effect=record_post), patch.object(
            agent.os, "system", side_effect=lambda _command: call_order.append("logout"),
        ) as logoff:
            deliver()
            handle_delivery(False, None)
            logoff.assert_called_once_with("shutdown /l /f")

        self.assertEqual(call_order, ["violation", "outbox", "logout"])
        self.assertEqual(instance._pending_fallback_violations, [])

    def test_monitor_tick_checkpoints_an_unchanged_foreground_app(self):
        instance = self.make_agent()
        started_at = agent._utc_now().replace(microsecond=0)
        instance._track_active_activity("notepad.exe", started_at)
        instance._find_new_process_match = Mock(return_value=None)
        with self.foreground_process(), patch.object(
            agent, "_utc_now", return_value=started_at + timedelta(seconds=30),
        ):
            instance.track_usage()
        instance._queue_outbox.assert_called_once()
        self.assertEqual(instance.current_activity_name, "notepad.exe")

    def test_window_title_changes_do_not_split_usage_or_leak_document_titles(self):
        instance = self.make_agent()
        instance._find_new_process_match = Mock(return_value=None)
        started_at = agent._utc_now().replace(microsecond=0)
        with self.foreground_process() as (window, process):
            for index, title in enumerate((
                "StarRail - Notepad", "private-document.txt", "Settings", "",
            )):
                window.title = title
                with patch.object(agent, "_utc_now", return_value=started_at + timedelta(seconds=5 * index)):
                    instance.track_usage()
                self.assertEqual(instance.current_activity_name, "notepad.exe")
            process.name.assert_not_called()

        instance._queue_outbox.assert_not_called()
        instance._close_current_activity(started_at + timedelta(seconds=20))
        payload = instance._queue_outbox.call_args.kwargs["payload"]
        segment = json.loads(payload["usage_data"])[0]
        self.assertEqual(segment["name"], "notepad.exe")
        self.assertEqual(segment["duration"], 20)
        self.assertEqual(set(segment), {"event_id", "name", "started_at", "ended_at", "duration"})

    def test_switching_real_executables_with_the_same_title_splits_usage(self):
        instance = self.make_agent()
        instance._find_new_process_match = Mock(return_value=None)
        started_at = agent._utc_now().replace(microsecond=0)
        for name, offset in (("notepad.exe", 0), ("chrome.exe", 10)):
            with self.foreground_process(
                exe_path=rf"C:\Apps\{name}", identity={"original_filename": name},
            ) as (window, _process), patch.object(
                agent, "_utc_now", return_value=started_at + timedelta(seconds=offset),
            ):
                window.title = "The same document title"
                instance.track_usage()
        instance._close_current_activity(started_at + timedelta(seconds=20))
        segments = [json.loads(call.kwargs["payload"]["usage_data"])[0]
                    for call in instance._queue_outbox.call_args_list]
        self.assertEqual([segment["name"] for segment in segments], ["notepad.exe", "chrome.exe"])
        self.assertEqual([segment["duration"] for segment in segments], [10, 10])
        self.assertEqual(segments[0]["ended_at"], segments[1]["started_at"])

    def test_usage_of_a_renamed_notepad_uses_its_original_executable_name(self):
        instance = self.make_agent()
        instance._find_new_process_match = Mock(return_value=None)
        with self.foreground_process(
            exe_path=r"C:\Apps\StarRail.exe", process_name="StarRail.exe",
        ):
            instance.track_usage()
        self.assertEqual(instance.current_activity_name, "notepad.exe")
        instance._finalize_violation.assert_not_called()

    def test_usage_without_metadata_falls_back_to_executable_basename(self):
        instance = self.make_agent()
        instance._find_new_process_match = Mock(return_value=None)
        with self.foreground_process(exe_path=r"C:\Tools\My-Editor.EXE", identity={}):
            instance.track_usage()
        self.assertEqual(instance.current_activity_name, "my-editor.exe")

    def test_usage_can_still_read_process_name_when_image_path_is_denied(self):
        instance = self.make_agent()
        instance._find_new_process_match = Mock(return_value=None)
        with self.foreground_process(process_name="NOTEPAD.EXE") as (_window, process), patch.object(
            agent, "read_executable_identity",
        ) as read_identity:
            process.exe.side_effect = agent.psutil.AccessDenied(123)
            instance.track_usage()
        self.assertEqual(instance.current_activity_name, "notepad.exe")
        read_identity.assert_not_called()

    def test_unreadable_or_exited_foreground_process_ends_the_previous_interval(self):
        for error in (agent.psutil.AccessDenied(123), agent.psutil.NoSuchProcess(123)):
            with self.subTest(error=type(error).__name__):
                instance = self.make_agent()
                instance._find_new_process_match = Mock(return_value=None)
                started_at = agent._utc_now().replace(microsecond=0)
                instance._track_active_activity("notepad.exe", started_at)
                with self.foreground_process() as (_window, process), patch.object(
                    agent, "_utc_now", return_value=started_at + timedelta(seconds=5),
                ):
                    process.exe.side_effect = error
                    process.name.side_effect = error
                    instance.track_usage()
                self.assertIsNone(instance.current_activity_name)
                instance._queue_outbox.assert_called_once()
                segment = json.loads(instance._queue_outbox.call_args.kwargs["payload"]["usage_data"])[0]
                self.assertEqual(segment["name"], "notepad.exe")
                self.assertEqual(segment["duration"], 5)

    def test_windows_system_processes_remain_excluded_from_usage(self):
        for name in ("SystemSettings.exe", "SearchHost.exe", "SearchApp.exe", "SearchUI.exe", "LockApp.exe"):
            with self.subTest(name=name):
                instance = self.make_agent()
                instance._find_new_process_match = Mock(return_value=None)
                with self.foreground_process(exe_path=rf"C:\Windows\{name}", identity={"original_filename": name}):
                    instance.track_usage()
                self.assertIsNone(instance.current_activity_name)
                instance._queue_outbox.assert_not_called()

    def test_desktop_and_taskbar_are_excluded_but_file_explorer_is_counted(self):
        for window_class, expected in (
            ("Progman", None), ("WorkerW", None), ("Shell_TrayWnd", None),
            ("Shell_SecondaryTrayWnd", None), ("CabinetWClass", "explorer.exe"),
        ):
            with self.subTest(window_class=window_class):
                instance = self.make_agent()
                instance._find_new_process_match = Mock(return_value=None)
                with self.foreground_process(
                    exe_path=r"C:\Windows\explorer.exe", identity={"original_filename": "EXPLORER.EXE"},
                    window_class=window_class,
                ):
                    instance.track_usage()
                self.assertEqual(instance.current_activity_name, expected)

    def test_missing_window_handle_never_falls_back_to_window_title(self):
        window = SimpleNamespace(title="StarRail", _hWnd=0)
        with patch.object(agent.psutil, "Process") as process:
            self.assertIsNone(agent._usage_name_for_window(window))
        process.assert_not_called()

    def test_window_class_is_read_using_a_64_bit_handle(self):
        handle = 0x100000001

        def get_class_name(observed_handle, output, length):
            self.assertEqual(observed_handle, handle)
            self.assertGreater(length, len("CabinetWClass"))
            output.value = "CabinetWClass"
            return len(output.value)

        user32 = SimpleNamespace(GetClassNameW=get_class_name)
        with patch.object(agent.ctypes, "windll", SimpleNamespace(user32=user32), create=True):
            self.assertEqual(agent._window_class_name(SimpleNamespace(_hWnd=handle)), "CabinetWClass")
        self.assertIs(get_class_name.argtypes[0], agent.ctypes.c_void_p)

    def test_agent_owned_window_is_not_recorded_as_an_application(self):
        instance = self.make_agent()
        instance.violation_state = SimpleNamespace(
            clear_expired_grace=Mock(return_value=False),
            is_grace_active=Mock(return_value=True),
        )
        with patch.object(agent, "_window_process_id", return_value=os.getpid()), patch.object(
            agent.gw, "getActiveWindow", return_value=SimpleNamespace(_hWnd=99, title="Renamed Agent"),
        ), patch.object(agent.psutil, "Process") as process:
            instance.track_usage()

        self.assertIsNone(instance.current_activity_name)
        instance._queue_outbox.assert_not_called()
        process.assert_not_called()

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
        self.assertIs(get_window_process_id.argtypes[0], agent.ctypes.c_void_p)

    @unittest.skipUnless(os.name == "nt", "Windows HWND ownership API")
    def test_native_message_window_is_identified_by_process_not_title(self):
        api = agent.ctypes.WinDLL("user32", use_last_error=True)
        create_window = api.CreateWindowExW
        create_window.argtypes = [
            agent.ctypes.c_ulong, agent.ctypes.c_wchar_p, agent.ctypes.c_wchar_p,
            agent.ctypes.c_ulong, agent.ctypes.c_int, agent.ctypes.c_int,
            agent.ctypes.c_int, agent.ctypes.c_int, agent.ctypes.c_void_p,
            agent.ctypes.c_void_p, agent.ctypes.c_void_p, agent.ctypes.c_void_p,
        ]
        create_window.restype = agent.ctypes.c_void_p
        destroy_window = api.DestroyWindow
        destroy_window.argtypes = [agent.ctypes.c_void_p]
        destroy_window.restype = agent.ctypes.c_int
        # HWND_MESSAGE creates an invisible window owned only by this test.
        handle = create_window(0, "STATIC", "StarRail - Notepad", 0, 0, 0, 0, 0,
                               agent.ctypes.c_void_p(-3), None, None, None)
        self.assertTrue(handle, f"CreateWindowExW failed: {agent.ctypes.get_last_error()}")
        try:
            window = SimpleNamespace(_hWnd=handle)
            self.assertEqual(agent._window_process_id(window), os.getpid())
            self.assertEqual(agent._window_class_name(window).casefold(), "static")
            with patch.object(agent.psutil, "Process") as process:
                self.assertIsNone(agent._usage_name_for_window(window))
            process.assert_not_called()
        finally:
            destroy_window(handle)

    def test_violation_metadata_is_saved_in_the_durable_payload(self):
        instance = self.make_agent()
        instance.report_violation(
            "blocked.exe", "Forbidden", detected_at="2026-10-22T10:00:00+00:00",
            policy_version="original-version", policy_token="original-receipt",
        )
        payload = instance._queue_outbox.call_args.kwargs["payload"]
        self.assertEqual(payload["detected_at"], "2026-10-22T10:00:00+00:00")
        self.assertEqual(payload["policy_token"], "original-receipt")


class AgentUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = agent.QApplication.instance() or agent.QApplication([])

    def test_session_end_button_is_hidden_until_info_bar_expands(self):
        bar = agent.SessionInfoBar("qa@example.com", None, 12)
        bar.show()
        self.app.processEvents()

        self.assertEqual(bar.size().width(), bar._compact_size[0])
        self.assertFalse(bar.logout_btn.isVisible())
        self.assertEqual(bar.toggle_btn.text(), "⌄")

        bar.toggle_btn.click()
        self.app.processEvents()
        self.assertTrue(bar.logout_btn.isVisible())
        self.assertEqual(bar.size().width(), bar._expanded_size[0])

        bar.toggle_btn.click()
        self.app.processEvents()
        self.assertFalse(bar.logout_btn.isVisible())
        bar.close()

    def test_login_error_label_wraps_long_messages(self):
        overlay = agent.LoginOverlay(SimpleNamespace(set_ui_references=Mock()))
        overlay.focus_timer.stop()

        self.assertTrue(overlay.error_label.wordWrap())
        overlay.close()

    def test_violation_prompt_explains_the_grace_period_and_repeat_warning(self):
        dialog = agent.ViolationDialog(
            "Blocked App",
            attempt=1,
            max_attempts=3,
            allow_grace=True,
            warning_seconds=15,
            grace_seconds=300,
        )
        dialog.timer.stop()

        self.assertIn("5 นาที", dialog.countdown_lbl.text())
        self.assertIn("แจ้งเตือนอีกครั้ง", dialog.countdown_lbl.text())
        dialog.close()

    def test_monitor_diagnostic_log_is_local_small_and_contains_no_raw_error(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            agent, "get_agent_data_dir", return_value=Path(temp_dir),
        ):
            agent._append_monitor_error_log("RuntimeError")
            log_path = Path(temp_dir) / "monitor-errors.log"

            self.assertTrue(log_path.exists())
            content = log_path.read_text(encoding="utf-8")
            size = log_path.stat().st_size

        self.assertIn("RuntimeError", content)
        self.assertNotIn("password", content.casefold())
        self.assertLess(size, 1024)


if __name__ == "__main__":
    unittest.main()
