import time
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from .logger import logger

# Hugging Face Space อาจ sleep อยู่ — retry ให้อัตโนมัติ
def post_with_retry(url, data=None, json_data=None, retries=3, timeout=15):
    for attempt in range(retries):
        try:
            if json_data:
                return requests.post(url, json=json_data, timeout=timeout)
            return requests.post(url, data=data, timeout=timeout)
        except requests.exceptions.ConnectionError:
            if attempt < retries - 1:
                time.sleep(3)
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(2)
    return None


class NetworkWorker(QThread):
    """Worker thread สำหรับ network calls — ป้องกัน GUI freeze."""
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn     = fn
        self._args   = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"NetworkWorker error: {e}", exc_info=True)
            self.error.emit(str(e))
