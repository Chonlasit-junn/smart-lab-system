import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from liveness_capture import collect_liveness


FACE = (20, 20, 80, 80)


class LivenessCaptureTests(unittest.TestCase):
    def collect(self, detections=None, scores=None, motion=3.0, frozen=False, stale=False, cancel=False):
        now = [0.0]
        def wait(delay):
            now[0] += delay
            return cancel
        frame = np.zeros((160, 160, 3), np.uint8)
        snapshot = lambda: SimpleNamespace(
            generation=1, sequence=1 if frozen else round(now[0] * 100),
            captured_at=-10 if stale else now[0], frame=frame,
        )
        detect = Mock(side_effect=detections) if detections else Mock(return_value=[FACE])
        predict = Mock(side_effect=scores) if scores else Mock(return_value=.95)
        motion_mock = Mock(side_effect=motion) if isinstance(motion, list) else Mock(return_value=motion)
        with patch('liveness_capture.face_motion_score', motion_mock):
            result = collect_liveness(
                snapshot=snapshot, detect=detect, predict=predict,
                is_current=lambda generation: generation == 1,
                stop_event=SimpleNamespace(wait=wait), generation=1, clock=lambda: now[0],
            )
        return result, predict, now[0]

    def test_one_missed_detection_is_replaced_with_a_fresh_valid_frame(self):
        result, predict, _ = self.collect(detections=[[FACE], [], [FACE], [FACE], [FACE], [FACE]])
        self.assertTrue(result.decision.accepted)
        self.assertEqual(predict.call_count, 5)

    def test_two_people_mid_scan_abort_even_after_good_samples(self):
        result, _, _ = self.collect(detections=[[FACE], [FACE], [FACE, (100, 20, 40, 40)]])
        self.assertFalse(result.decision.accepted)
        self.assertEqual(result.decision.reason, 'multiple_faces')

    def test_subject_leaving_track_aborts(self):
        result, _, _ = self.collect(detections=[[FACE], [(110, 100, 40, 40)]])
        self.assertEqual(result.decision.reason, 'face_changed')

    def test_stale_and_repeated_camera_frames_never_count_as_five_samples(self):
        for options in ({'frozen': True}, {'stale': True}):
            with self.subTest(options=options):
                result, _, elapsed = self.collect(**options)
                self.assertFalse(result.decision.accepted)
                self.assertEqual(result.decision.reason, 'insufficient_samples')
                self.assertLess(elapsed, 3.2)

    def test_static_high_scoring_face_is_rejected_after_bounded_response_time(self):
        result, predict, elapsed = self.collect(motion=0)
        self.assertEqual(result.decision.reason, 'no_motion')
        self.assertEqual(predict.call_count, 5)
        self.assertGreaterEqual(elapsed, 3)

    def test_bad_liveness_scores_are_not_replaced_until_lucky_predictions_pass(self):
        result, predict, _ = self.collect(scores=[.95, .1, .95, .2, .95])
        self.assertEqual(result.decision.reason, 'insufficient_liveness_passes')
        self.assertEqual(predict.call_count, 5)

    def test_user_has_time_to_respond_after_the_first_five_frames(self):
        result, predict, elapsed = self.collect(motion=[0, 0, 0, 0, 3, 3])
        self.assertTrue(result.decision.accepted)
        self.assertEqual(predict.call_count, 5)
        self.assertGreater(elapsed, .6)

    def test_one_motion_spike_is_not_enough(self):
        result, _, _ = self.collect(motion=[3] + [0] * 30)
        self.assertFalse(result.decision.accepted)
        self.assertEqual(result.decision.reason, 'no_motion')

    def test_cancellation_returns_no_access_decision(self):
        result, _, _ = self.collect(cancel=True)
        self.assertIsNone(result)
