import sys
import threading
import queue
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

if sys.platform == "win32":
    import smart_gatekeeper as kiosk


@unittest.skipUnless(sys.platform == "win32", "Gatekeeper uses Windows camera/UI APIs")
class GatekeeperAccessFlowTests(unittest.TestCase):
    def test_startup_selects_saved_camera_before_starting_hardware(self):
        instance = SimpleNamespace(
            _scanner_started=False, geometry=Mock(), _setup_ui=Mock(), _init_hardware=Mock(),
        )
        with patch.object(kiosk, "load_camera_index", return_value=3):
            kiosk.GatekeeperDemo._start_scanner(instance)
        self.assertEqual(instance._current_cam_index, 3)
        self.assertEqual(instance._available_cameras, {3: "Camera 3"})
        instance._init_hardware.assert_called_once()

    def test_camera_selection_is_saved_once_after_success_and_stale_frames_do_not_save(self):
        instance = SimpleNamespace(
            _camera=SimpleNamespace(index=3, generation=2), _remembered_camera_index=0,
        )
        with patch.object(kiosk, "save_camera_index") as save:
            kiosk.GatekeeperDemo._remember_camera(instance, 1)
            save.assert_not_called()
            kiosk.GatekeeperDemo._remember_camera(instance, 2)
            kiosk.GatekeeperDemo._remember_camera(instance, 2)
            save.assert_called_once_with(3)

    def test_camera_search_is_not_started_during_access_verification(self):
        instance = SimpleNamespace(is_scanning=True, sub_label=Mock(), _camera=Mock())
        kiosk.GatekeeperDemo._refresh_cameras(instance)
        instance._camera.request_discovery.assert_not_called()

    def test_explicit_search_invalidates_old_faces_before_discovery(self):
        instance = SimpleNamespace(
            is_scanning=False, in_cooldown=False, _camera=Mock(),
            _last_faces=[(0, 0, 10, 10)], _set_status=Mock(),
        )
        kiosk.GatekeeperDemo._refresh_cameras(instance)
        self.assertEqual(instance._last_faces, [])
        instance._camera.request_discovery.assert_called_once()

    def test_preview_reuses_ctk_image_and_does_not_draw_on_raw_camera_frame(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame.flags.writeable = False
        packet = SimpleNamespace(frame=frame, generation=0, sequence=1)
        instance = SimpleNamespace(
            _stop_event=threading.Event(), _sync_camera=Mock(),
            _camera=SimpleNamespace(snapshot=lambda: packet), _preview_sequence=None,
            _preview_image=None, models_loaded=False, video_label=Mock(),
            after=Mock(), _display_loop=Mock(), _remember_camera=Mock(),
        )
        with patch.object(kiosk.ctk, "CTkImage") as images, patch.object(
            kiosk.Image, "fromarray", wraps=kiosk.Image.fromarray,
        ) as pil:
            kiosk.GatekeeperDemo._display_loop(instance)
            packet.sequence = 2
            kiosk.GatekeeperDemo._display_loop(instance)
            kiosk.GatekeeperDemo._display_loop(instance)  # same captured frame: no redraw
            images.assert_called_once()
            self.assertEqual(pil.call_count, 2)
            images.return_value.configure.assert_called_once()
        self.assertFalse(frame.any())

    def test_worker_posts_without_calling_tk_and_old_camera_grant_is_discarded(self):
        grant = Mock()
        instance = SimpleNamespace(
            _stop_event=threading.Event(), _ui_events=queue.Queue(),
            _camera=SimpleNamespace(generation=2), after=Mock(), _drain_ui_events=Mock(),
        )
        kiosk.GatekeeperDemo._post_ui(instance, grant, generation=1)
        instance.after.assert_not_called()
        kiosk.GatekeeperDemo._drain_ui_events(instance)
        grant.assert_not_called()
        instance._stop_event.set()
        kiosk.GatekeeperDemo._post_ui(instance, grant, generation=2)
        self.assertTrue(instance._ui_events.empty())

    def test_stopping_or_switching_camera_cancels_scan_before_inference_and_http(self):
        instance = SimpleNamespace(
            _scan_is_current=Mock(return_value=False), _identify_face=Mock(),
            anti_spoof=Mock(), _post_ui=Mock(),
        )
        frame = np.zeros((80, 80, 3), dtype=np.uint8)
        kiosk.GatekeeperDemo._run_liveness(instance, frame, frame, 1)
        instance.anti_spoof.predict.assert_not_called()
        instance._identify_face.assert_not_called()

    def test_shutdown_signals_workers_and_waits_without_releasing_camera_on_tk_thread(self):
        instance = SimpleNamespace(
            _stop_event=threading.Event(), _camera=Mock(), _scan_client=Mock(),
            _start_worker=Mock(), _finish_closing=Mock(),
        )
        kiosk.GatekeeperDemo.on_closing(instance)
        self.assertTrue(instance._stop_event.is_set())
        instance._camera.stop.assert_called_once()
        instance._start_worker.assert_called_once_with(instance._scan_client.close)
        instance._finish_closing.assert_called_once()

    def test_detection_from_a_stale_frame_cannot_start_a_scan(self):
        instance = SimpleNamespace(is_scanning=False, _last_faces=[], _faces_at=0)
        packet = SimpleNamespace(captured_at=time.monotonic() - 2)
        kiosk.GatekeeperDemo._accept_faces(instance, packet, [(0, 0, 10, 10)])
        self.assertEqual(instance._last_faces, [])

    def test_local_motion_failure_is_sent_for_audit_and_never_grants_access(self):
        frame = np.zeros((80, 80, 3), dtype=np.uint8)
        instance = SimpleNamespace(
            _stop_event=SimpleNamespace(wait=Mock(return_value=False)),
            _scan_is_current=Mock(return_value=True), _post_ui=Mock(),
            model_path="synthetic-model",
            anti_spoof=SimpleNamespace(predict=Mock(return_value=np.array([[0.01, 0.98, 0.01]]))),
            _get_latest_frame=Mock(return_value=frame),
            _detect_faces=Mock(return_value=[(0, 0, 80, 80)]),
            _crop_face=Mock(return_value=frame),
            _frame_motion_score=Mock(return_value=0.0),
            _identify_face=Mock(return_value=(False, "no motion")),
            _show_identity_result=Mock(),
            _reset_state=Mock(),
            after=Mock(),
        )
        with patch.object(kiosk.time, "sleep"):
            kiosk.GatekeeperDemo._run_liveness(instance, frame, frame, 0)
        args, kwargs = instance._identify_face.call_args
        self.assertIsNone(args[0])
        self.assertIs(kwargs["liveness_passed"], False)
        self.assertEqual(kwargs["liveness_reason"], "no_motion")
        self.assertEqual(instance._post_ui.call_args.args[:2], (instance._show_identity_result, False))

    def test_mock_action_is_disabled_by_default(self):
        instance = SimpleNamespace(_set_status=Mock(), after=Mock())
        with patch.object(kiosk, "DEV_MOCK_ENABLED", False):
            kiosk.GatekeeperDemo._force_result(instance, True)
        instance._set_status.assert_not_called()
        instance.after.assert_not_called()

    def test_enabled_ui_mock_does_not_display_an_access_grant(self):
        instance = SimpleNamespace(
            score_bar=Mock(), score_pct_label=Mock(), score_badge=Mock(),
            _set_status=Mock(), after=Mock(), _reset_state=Mock(),
        )
        with patch.object(kiosk.threading, "Thread"):
            kiosk.GatekeeperDemo._show_result(instance, True, 0.95)
        self.assertEqual(instance._set_status.call_args.args[0], "DEMO: REAL FACE")
        self.assertNotIn("ACCESS GRANTED", instance._set_status.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
