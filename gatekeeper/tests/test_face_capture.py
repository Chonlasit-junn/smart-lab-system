from pathlib import Path
import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from camera_stream import CameraStream
from face_capture import FaceDetector, crop_face, face_motion_score, same_face_track


class FaceCaptureTests(unittest.TestCase):
    def test_detector_keeps_two_distinct_faces_including_partially_overlapping_boxes(self):
        detector = object.__new__(FaceDetector)
        detector.net = Mock()
        detector.net.forward.return_value = np.array([
            [0, 1, .95, .1, .1, .5, .7], [0, 1, .91, .35, .1, .75, .7],
            [0, 1, .1, 0, 0, 1, 1],
        ])
        self.assertEqual(len(detector.detect(np.zeros((480, 640, 3), np.uint8))), 2)

    def test_public_single_face_duplicate_haar_reproduction_and_two_face_scene(self):
        root = Path(__file__).resolve().parents[1]
        detector = FaceDetector(root)
        source = cv2.imread(str(root / 'Silent-Face-Anti-Spoofing/images/sample/image_T1.jpg'))
        canvas = np.full((480, 640, 3), 80, np.uint8)
        portrait = cv2.resize(source, (360, 480))
        canvas[:, 140:500] = portrait
        matrix = cv2.getRotationMatrix2D((320, 240), 10, .8)
        transformed = cv2.warpAffine(canvas, matrix, (640, 480), borderValue=(80, 80, 80))
        self.assertEqual(len(detector.detect(transformed)), 1)
        two = np.concatenate([portrait, portrait], axis=1)
        self.assertEqual(len(detector.detect(two)), 2)

    def test_motion_tracks_translation_but_not_brightness_or_detector_box_jitter(self):
        rng = np.random.default_rng(42)
        frame = rng.integers(30, 200, (200, 200, 3), dtype=np.uint8)
        moved = cv2.warpAffine(frame, np.float32([[1, 0, 6], [0, 1, 0]]), (200, 200))
        self.assertGreater(face_motion_score(frame, moved, (40, 40, 100, 100)), 2)
        brighter = (frame.astype(np.int16) + 3).astype(np.uint8)
        self.assertLess(face_motion_score(frame, brighter, (40, 40, 100, 100)), .1)
        self.assertLess(face_motion_score(frame, frame, (42, 40, 100, 100)), .1)

    def test_crop_keeps_upstream_context_at_image_edge(self):
        image = np.zeros((480, 640, 3), np.uint8)
        crop = crop_face(image, (0, 0, 100, 100))
        self.assertEqual(crop.shape[:2], (271, 271))

    def test_large_subject_change_requires_a_new_scan(self):
        self.assertFalse(same_face_track((0, 0, 100, 100), (200, 0, 100, 100)))

    def test_camera_keeps_raw_orientation_and_owns_immutable_copy(self):
        stream = CameraStream()
        image = np.zeros((10, 20, 3), np.uint8)
        image[:, :5] = 100
        stream._publish(image, 0)
        packet = stream.snapshot()
        np.testing.assert_array_equal(packet.frame, image)
        image[:] = 0
        self.assertEqual(int(packet.frame[0, 0, 0]), 100)
        self.assertFalse(packet.frame.flags.writeable)
