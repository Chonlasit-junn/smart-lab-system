import unittest

from liveness_policy import evaluate_liveness


class LivenessPolicyTests(unittest.TestCase):
    def test_real_face_with_small_motion_passes(self):
        decision = evaluate_liveness(
            [0.80, 0.79, 0.83, 0.77, 0.81],
            [0.0, 2.4, 1.8, 0.7],
            threshold=0.72,
            required_samples=5,
            required_passes=4,
            min_motion_score=2.0,
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.passed_samples, 5)
        self.assertTrue(decision.motion_detected)

    def test_static_phone_image_is_rejected_even_with_high_scores(self):
        decision = evaluate_liveness(
            [0.91, 0.90, 0.92, 0.90, 0.91],
            [0.0, 0.2, 0.4, 0.3],
            threshold=0.72,
            required_samples=5,
            required_passes=4,
            min_motion_score=2.0,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "no_motion")

    def test_liveness_consensus_rejects_too_many_low_scores(self):
        decision = evaluate_liveness(
            [0.80, 0.71, 0.69, 0.78, 0.70],
            [0.0, 2.5, 2.1, 1.9],
            threshold=0.72,
            required_samples=5,
            required_passes=4,
            min_motion_score=2.0,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "insufficient_liveness_passes")

    def test_missing_samples_are_rejected(self):
        decision = evaluate_liveness(
            [0.82, 0.84],
            [0.0, 2.4],
            threshold=0.72,
            required_samples=5,
            required_passes=4,
            min_motion_score=2.0,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "insufficient_samples")

    def test_out_of_range_scores_do_not_count_as_samples(self):
        decision = evaluate_liveness(
            [0.80, 1.4, -0.2, 0.79, 0.81],
            [0.0, 2.4, 2.2],
            threshold=0.72,
            required_samples=5,
            required_passes=4,
            min_motion_score=2.0,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.sample_count, 3)
        self.assertEqual(decision.reason, "insufficient_samples")


if __name__ == "__main__":
    unittest.main()
