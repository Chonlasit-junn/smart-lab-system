import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from camera_stream import CameraFrame, CameraStream


def wait_for(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("Camera worker did not reach expected state")
        time.sleep(0.002)


class CameraStreamTests(unittest.TestCase):
    def test_slow_driver_open_does_not_block_ui_and_releases_failed_handle(self):
        entered, finish = threading.Event(), threading.Event()
        handles = []

        class Camera:
            released = False
            def __init__(self, index, *_args):
                handles.append(self)
                entered.set()
                finish.wait(2)
            def isOpened(self): return False
            def release(self): self.released = True

        with patch("camera_stream.cv2.VideoCapture", Camera):
            stream = CameraStream()
            stream.start()
            try:
                self.assertTrue(entered.wait(1))
                self.assertIsNone(stream.snapshot())
            finally:
                stream.stop()
                finish.set()
                stream.join(1)
            self.assertFalse(stream.is_alive())
            self.assertTrue(all(handle.released for handle in handles))

    def test_switch_uses_one_owner_and_never_returns_previous_camera_frame(self):
        operations = []

        class Camera:
            def __init__(self, index, *_args):
                self.index = index
                operations.append((threading.get_ident(), "open", index))
            def isOpened(self): return self.index in (0, 2)
            def set(self, *_args): pass
            def release(self): operations.append((threading.get_ident(), "release", self.index))
            def read(self):
                time.sleep(0.002)
                return True, np.full((4, 4, 3), self.index, dtype=np.uint8)

        with patch("camera_stream.cv2.VideoCapture", Camera):
            stream = CameraStream()
            stream.start()
            try:
                wait_for(lambda: stream.snapshot() is not None)
                first = stream.snapshot()
                self.assertFalse(first.frame.flags.writeable)
                stream.select(2)
                second = stream.snapshot()
                self.assertTrue(second is None or second.generation != first.generation)
                wait_for(lambda: stream.snapshot() is not None)
                second = stream.snapshot()
                self.assertEqual(second.generation, stream.generation)
                self.assertTrue((second.frame == 2).all())
                stream.request_discovery()
                wait_for(lambda: not stream.discovering)
                self.assertEqual(set(stream.available), {0, 2})
            finally:
                stream.stop()
                stream.join(1)
            self.assertFalse(stream.is_alive())
            self.assertIsNone(stream.snapshot())
            self.assertEqual(len({owner for owner, _, _ in operations}), 1)

    def test_stale_snapshot_is_not_eligible_for_detection(self):
        stream = CameraStream()
        stream._latest = CameraFrame(0, 1, time.monotonic() - 2, object())
        self.assertIsNone(stream.snapshot())

    def test_camera_disconnect_invalidates_in_flight_scan_generation(self):
        disconnect = threading.Event()
        class Camera:
            reads = 0
            def __init__(self, index, *_args): self.index = index
            def isOpened(self): return self.index == 0
            def release(self): pass
            def set(self, *_args): pass
            def read(self):
                self.reads += 1
                if self.reads == 1:
                    return True, np.zeros((4, 4, 3), dtype=np.uint8)
                disconnect.wait(1)
                return False, None
        with patch("camera_stream.cv2.VideoCapture", Camera):
            stream = CameraStream()
            stream.start()
            try:
                wait_for(lambda: stream.snapshot() is not None)
                generation = stream.generation
                disconnect.set()
                wait_for(lambda: stream.generation != generation)
                self.assertIsNone(stream.snapshot())
            finally:
                stream.stop()
                disconnect.set()
                stream.join(1)

    def test_missing_preferred_camera_falls_back_to_existing_camera(self):
        class Camera:
            def __init__(self, index, *_args): self.index = index
            def isOpened(self): return self.index == 3
            def release(self): pass
            def set(self, *_args): pass
            def read(self):
                time.sleep(0.002)
                return True, np.zeros((4, 4, 3), dtype=np.uint8)
        stream = CameraStream()
        with patch("camera_stream.cv2.VideoCapture", Camera):
            stream.start()
            try:
                wait_for(lambda: stream.snapshot() is not None)
                self.assertEqual(stream.index, 3)
                self.assertEqual(stream.generation, 1)
            finally:
                stream.stop()
                stream.join(1)

    def test_selected_camera_produces_first_frame_without_probing_other_indices(self):
        for selected in (0, 3):
            opened = []
            class Camera:
                def __init__(self, index, *_args):
                    opened.append(index)
                    self.index = index
                def isOpened(self): return self.index == selected
                def release(self): pass
                def set(self, *_args): pass
                def read(self):
                    time.sleep(0.002)
                    return True, np.zeros((4, 4, 3), dtype=np.uint8)
            with self.subTest(selected=selected), patch("camera_stream.cv2.VideoCapture", Camera):
                stream = CameraStream(selected)
                stream.start()
                try:
                    wait_for(lambda: stream.snapshot() is not None)
                    self.assertEqual(opened, [selected])
                    self.assertEqual(stream.available, {selected: f"Camera {selected}"})
                finally:
                    stream.stop()
                    stream.join(1)

    def test_backend_fallback_reuses_selected_index_and_manual_discovery_skips_active_handle(self):
        opened = []
        class Camera:
            def __init__(self, index, api):
                self.index, self.api = index, api
                opened.append((index, api))
            def isOpened(self): return self.api == 222 and self.index in (0, 2)
            def release(self): pass
            def set(self, *_args): pass
            def read(self):
                time.sleep(0.002)
                return True, np.zeros((4, 4, 3), dtype=np.uint8)
        with patch("camera_stream.cv2.VideoCapture", Camera):
            stream = CameraStream()
            stream._backends = (111, 222)
            stream.start()
            try:
                wait_for(lambda: stream.snapshot() is not None)
                self.assertEqual(opened, [(0, 111), (0, 222)])
                old_generation = stream.generation
                stream.request_discovery()
                self.assertNotEqual(stream.generation, old_generation)
                wait_for(lambda: not stream.discovering)
                self.assertEqual(set(stream.available), {0, 2})
                self.assertEqual(opened.count((0, 222)), 1)
                wait_for(lambda: stream.snapshot() is not None)
            finally:
                stream.stop()
                stream.join(1)

    def test_selection_changed_during_discovery_cannot_relabel_old_camera_pixels(self):
        probing, finish = threading.Event(), threading.Event()
        class Camera:
            def __init__(self, index, *_args):
                self.index = index
                if index == 1:
                    probing.set()
                    finish.wait(2)
            def isOpened(self): return self.index in (0, 2)
            def release(self): pass
            def set(self, *_args): pass
            def read(self):
                time.sleep(0.002)
                return True, np.full((4, 4, 3), self.index, dtype=np.uint8)
        with patch("camera_stream.cv2.VideoCapture", Camera):
            stream = CameraStream()
            stream.start()
            try:
                wait_for(lambda: stream.snapshot() is not None)
                stream.request_discovery()
                self.assertTrue(probing.wait(1))
                stream.select(2)
                finish.set()
                wait_for(lambda: stream.snapshot() is not None)
                packet = stream.snapshot()
                self.assertEqual(packet.generation, stream.generation)
                self.assertTrue((packet.frame == 2).all())
            finally:
                finish.set()
                stream.stop()
                stream.join(1)

    def test_transient_empty_startup_frames_do_not_reopen_working_camera(self):
        opened = []
        class Camera:
            def __init__(self, index, *_args):
                opened.append(index)
                self.reads = 0
            def isOpened(self): return True
            def release(self): pass
            def set(self, *_args): pass
            def read(self):
                self.reads += 1
                if self.reads < 3:
                    return False, None
                time.sleep(0.002)
                return True, np.zeros((4, 4, 3), dtype=np.uint8)
        with patch("camera_stream.cv2.VideoCapture", Camera):
            stream = CameraStream()
            stream.start()
            try:
                wait_for(lambda: stream.snapshot() is not None)
                self.assertEqual(opened, [0])
            finally:
                stream.stop()
                stream.join(1)
