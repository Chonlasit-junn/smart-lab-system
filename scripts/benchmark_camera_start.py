"""Measure first-frame latency with simulated drivers; no real camera/API/DB."""

import argparse
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gatekeeper"))
from camera_stream import CameraStream


def measure(preferred, active):
    opened = []
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    class Camera:
        def __init__(self, index, *_args):
            self.index = index
            opened.append(index)
            time.sleep(0.02 if index == active else 0.1)
        def isOpened(self): return self.index == active
        def set(self, *_args): return True
        def release(self): pass
        def read(self):
            time.sleep(0.005)
            return self.index == active, frame.copy() if self.index == active else None
    stream = CameraStream(preferred)
    with patch("camera_stream.cv2.VideoCapture", Camera):
        started = time.perf_counter()
        stream.start()
        try:
            while stream.snapshot() is None:
                if time.perf_counter() - started > 5:
                    raise TimeoutError("No simulated first frame")
                time.sleep(0.001)
            elapsed = (time.perf_counter() - started) * 1000
            first_opens = list(opened)
        finally:
            stream.stop()
            stream.join(2)
        assert not stream.is_alive()
    return {"preferred_index": preferred, "active_index": active, "first_frame_ms": elapsed,
            "camera_opens_before_first_frame": first_opens}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = {"scope": "synthetic first-frame latency; active open 20 ms, unused open 100 ms, read 5 ms",
              "measurements": [measure(0, 0), measure(3, 3), measure(0, 3)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
