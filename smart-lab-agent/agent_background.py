"""Run blocking Agent operations away from Qt's UI thread."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot


class _WorkerSignals(QObject):
    completed = pyqtSignal(str, object, object)


class _CallableWorker(QRunnable):
    def __init__(self, key: str, operation: Callable[[], Any]):
        super().__init__()
        self.setAutoDelete(False)
        self.key = key
        self.operation = operation
        self.signals = _WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = self.operation()
        except Exception as error:
            self.signals.completed.emit(self.key, None, error)
        else:
            self.signals.completed.emit(self.key, result, None)


class BackgroundTaskRunner(QObject):
    """Serialize duplicate task keys and deliver callbacks on the Qt thread."""

    def __init__(self, parent: Optional[QObject] = None, max_threads: int = 3):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, int(max_threads)))
        self._workers: dict[str, _CallableWorker] = {}
        self._callbacks: dict[str, Callable[[Any, Optional[Exception]], None]] = {}

    def submit(
        self,
        key: str,
        operation: Callable[[], Any],
        callback: Callable[[Any, Optional[Exception]], None],
    ) -> bool:
        """Submit one operation; return False if that key is already active."""
        if key in self._workers:
            return False

        worker = _CallableWorker(key, operation)
        worker.signals.completed.connect(self._on_completed)
        self._workers[key] = worker
        self._callbacks[key] = callback
        self._pool.start(worker)
        return True

    @pyqtSlot(str, object, object)
    def _on_completed(self, key: str, result: Any, error: Optional[Exception]):
        self._workers.pop(key, None)
        callback = self._callbacks.pop(key, None)
        if callback is None:
            return
        try:
            callback(result, error)
        except Exception as callback_error:
            print(f"Background task callback failed [{key}]: {callback_error}")
