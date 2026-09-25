import os
import sys
import threading
import unittest
from pathlib import Path


AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from agent_background import BackgroundTaskRunner  # noqa: E402


class BackgroundTaskRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.runner = BackgroundTaskRunner(max_threads=2)

    def _run_until_callback(self, submit):
        loop = QEventLoop()
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(3000)
        submit(loop)
        loop.exec()
        self.runner._pool.waitForDone(1000)
        self.assertTrue(timeout.isActive(), "background task did not finish before timeout")

    def test_operation_runs_off_thread_and_callback_returns_to_qt_thread(self):
        main_thread_id = threading.get_ident()
        result = {}

        def submit(loop):
            def complete(value, error):
                result.update(value=value, error=error, callback_thread=threading.get_ident())
                loop.quit()

            self.runner.submit(
                "thread-check",
                lambda: threading.get_ident(),
                complete,
            )

        self._run_until_callback(submit)

        self.assertIsNone(result["error"])
        self.assertNotEqual(result["value"], main_thread_id)
        self.assertEqual(result["callback_thread"], main_thread_id)

    def test_duplicate_key_is_coalesced_and_errors_reach_callback(self):
        result = {}

        def submit(loop):
            first = self.runner.submit(
                "single-flight",
                lambda: (_ for _ in ()).throw(RuntimeError("offline")),
                lambda value, error: (result.update(value=value, error=error), loop.quit()),
            )
            second = self.runner.submit("single-flight", lambda: "duplicate", lambda *_: None)
            result.update(first=first, second=second)

        self._run_until_callback(submit)

        self.assertTrue(result["first"])
        self.assertFalse(result["second"])
        self.assertIsNone(result["value"])
        self.assertIsInstance(result["error"], RuntimeError)
        self.assertEqual(str(result["error"]), "offline")


if __name__ == "__main__":
    unittest.main()
