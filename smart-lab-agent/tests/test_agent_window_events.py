import unittest

from agent_window_events import (
    EVENT_OBJECT_DESTROY,
    EVENT_OBJECT_HIDE,
    EVENT_OBJECT_SHOW,
    WindowVisibilityTracker,
)


class WindowVisibilityTrackerTests(unittest.TestCase):
    def test_close_and_reopen_between_polling_ticks_is_retained(self):
        tracker = WindowVisibilityTracker()
        tracker.seed_visible_window(100, 42)

        tracker.handle_event(EVENT_OBJECT_HIDE, 100, 42)
        tracker.handle_event(EVENT_OBJECT_SHOW, 100, 42)

        self.assertEqual(tracker.consume_shown_process_ids(), {42})
        self.assertEqual(tracker.consume_shown_process_ids(), set())

    def test_other_visible_window_prevents_false_reopen(self):
        tracker = WindowVisibilityTracker()
        tracker.seed_visible_window(100, 42)
        tracker.seed_visible_window(101, 42)

        tracker.handle_event(EVENT_OBJECT_HIDE, 100, 42)
        tracker.handle_event(EVENT_OBJECT_SHOW, 100, 42)

        self.assertEqual(tracker.consume_shown_process_ids(), set())

    def test_destroyed_last_window_then_new_window_counts_as_reopen(self):
        tracker = WindowVisibilityTracker()
        tracker.seed_visible_window(100, 42)

        tracker.handle_event(EVENT_OBJECT_DESTROY, 100, 42)
        tracker.handle_event(EVENT_OBJECT_SHOW, 200, 42)

        self.assertEqual(tracker.consume_shown_process_ids(), {42})

    def test_destroy_event_cleans_up_when_windows_api_cannot_resolve_pid(self):
        tracker = WindowVisibilityTracker()
        tracker.seed_visible_window(100, 42)

        tracker.handle_event(EVENT_OBJECT_DESTROY, 100, None)
        tracker.handle_event(EVENT_OBJECT_SHOW, 200, 42)

        self.assertEqual(tracker.consume_shown_process_ids(), {42})

    def test_ignores_non_window_accessibility_events(self):
        tracker = WindowVisibilityTracker()
        tracker.handle_event(EVENT_OBJECT_SHOW, 100, 42, object_id=-4)
        tracker.handle_event(EVENT_OBJECT_SHOW, 100, 42, child_id=1)

        self.assertEqual(tracker.consume_shown_process_ids(), set())

    def test_prune_removes_stale_pids_and_pending_events(self):
        tracker = WindowVisibilityTracker()
        tracker.seed_visible_window(100, 42)
        tracker.handle_event(EVENT_OBJECT_HIDE, 100, 42)
        tracker.handle_event(EVENT_OBJECT_SHOW, 100, 42)

        tracker.prune({7})

        self.assertEqual(tracker.consume_shown_process_ids(), set())


if __name__ == "__main__":
    unittest.main()
