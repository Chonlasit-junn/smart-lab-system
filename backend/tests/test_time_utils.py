import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from time_utils import as_lab_naive, as_utc  # noqa: E402


class TimeNormalizationTests(unittest.TestCase):
    def test_legacy_naive_agent_time_is_interpreted_as_lab_time(self):
        legacy_local = datetime(2026, 9, 22, 0, 30)

        self.assertEqual(
            as_utc(legacy_local),
            datetime(2026, 9, 21, 17, 30, tzinfo=timezone.utc),
        )

    def test_utc_event_keeps_the_same_lab_calendar_date(self):
        event_time = datetime(2026, 9, 21, 17, 30, tzinfo=timezone.utc)

        lab_time = as_lab_naive(event_time)

        self.assertEqual(lab_time, datetime(2026, 9, 22, 0, 30))
        self.assertEqual(lab_time.date(), date(2026, 9, 22))


if __name__ == "__main__":
    unittest.main()
