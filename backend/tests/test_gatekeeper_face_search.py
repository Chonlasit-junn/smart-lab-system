import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers.gatekeeper import (  # noqa: E402
    FACE_SEARCH_BATCH_SIZE,
    _find_closest_face_user,
)


class GatekeeperFaceSearchTests(unittest.TestCase):
    def test_vectorized_search_returns_nearest_valid_embedding(self):
        users = [
            SimpleNamespace(id=1, face_embedding=[0.0, 1.0, 0.0]),
            SimpleNamespace(id=2, face_embedding=[0.99, 0.1, 0.0]),
            SimpleNamespace(id=3, face_embedding=[float("nan"), 0.0, 1.0]),
            SimpleNamespace(id=4, face_embedding=[1.0, 0.0]),
            SimpleNamespace(id=5, face_embedding=[0.0, 0.0, 0.0]),
        ]

        match, distance = _find_closest_face_user(users, [1.0, 0.0, 0.0])

        self.assertEqual(match.id, 2)
        self.assertAlmostEqual(distance, 1.0 - (0.99 / (0.99**2 + 0.1**2) ** 0.5), places=6)

    def test_invalid_probe_or_no_valid_candidates_returns_no_match(self):
        users = [
            SimpleNamespace(face_embedding=None),
            SimpleNamespace(face_embedding=[0.0, 0.0]),
            SimpleNamespace(face_embedding=[float("inf"), 1.0]),
        ]

        self.assertEqual(_find_closest_face_user(users, [1.0, 0.0]), (None, None))
        self.assertEqual(_find_closest_face_user(users, [float("nan"), 0.0]), (None, None))

    def test_search_compares_multiple_batches_without_losing_best_match(self):
        users = (
            SimpleNamespace(id=index, face_embedding=[0.0, 1.0])
            for index in range(FACE_SEARCH_BATCH_SIZE)
        )

        def all_users():
            yield from users
            yield SimpleNamespace(id=FACE_SEARCH_BATCH_SIZE + 1, face_embedding=[1.0, 0.0])

        match, distance = _find_closest_face_user(all_users(), [1.0, 0.0])

        self.assertEqual(match.id, FACE_SEARCH_BATCH_SIZE + 1)
        self.assertAlmostEqual(distance, 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
