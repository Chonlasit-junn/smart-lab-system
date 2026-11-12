import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_clock import ServerClock


class ServerClockTests(unittest.TestCase):
    def test_backend_anchor_ignores_windows_wall_clock_changes(self):
        wall_time = [datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)]
        monotonic_time = [50.0]
        clock = ServerClock(
            wall_clock=lambda: wall_time[0],
            monotonic_clock=lambda: monotonic_time[0],
        )
        server_anchor = datetime(2026, 11, 11, 2, 0, tzinfo=timezone.utc)

        self.assertTrue(clock.sync(server_anchor.isoformat()))
        monotonic_time[0] += 90
        wall_time[0] = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)

        self.assertEqual(clock.now_utc(), server_anchor + timedelta(seconds=90))

    def test_rejects_naive_or_malformed_server_timestamps(self):
        clock = ServerClock(monotonic_clock=lambda: 1.0)

        self.assertFalse(clock.sync("2026-11-11T02:00:00"))
        self.assertFalse(clock.sync("not-a-timestamp"))
        self.assertFalse(clock.sync(None))

    def test_uses_local_utc_clock_until_backend_time_is_available(self):
        local_time = datetime(2026, 11, 11, 2, 0, tzinfo=timezone.utc)
        clock = ServerClock(wall_clock=lambda: local_time)

        self.assertEqual(clock.now_utc(), local_time)


if __name__ == "__main__":
    unittest.main()
