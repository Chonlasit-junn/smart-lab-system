import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

from routers import agent  # noqa: E402


class AgentTimeParsingTests(unittest.TestCase):
    def test_new_agent_timestamp_is_normalized_to_utc(self):
        parsed = agent._parse_usage_time(
            "2026-09-22T00:30:00+07:00",
            datetime(2026, 9, 22, 0, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(
            parsed,
            datetime(2026, 9, 21, 17, 30, tzinfo=timezone.utc),
        )

    def test_legacy_agent_timestamp_without_offset_is_treated_as_lab_time(self):
        parsed = agent._parse_usage_time(
            "2026-09-22T00:30:00",
            datetime(2026, 9, 22, 0, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(
            parsed,
            datetime(2026, 9, 21, 17, 30, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
