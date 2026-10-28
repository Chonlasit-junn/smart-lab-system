"""One owner for native camera handles; immutable, fresh frame snapshots."""

from dataclasses import dataclass
import threading
import sys
import time

import cv2


@dataclass(frozen=True)
class CameraFrame:
    generation: int
    sequence: int
    captured_at: float
    frame: object


class CameraStream:
    def __init__(self, index=0, *, stop_event=None):
        self._stop = stop_event if stop_event is not None else threading.Event()
        self._lock = threading.Lock()
        self._index = index
        self._generation = 0
        self._sequence = 0
        self._latest = None
        self._available = {index: f"Camera {index}"}
        self._search_requested = threading.Event()
        self._discovering = False
        self._backends = (cv2.CAP_DSHOW, cv2.CAP_ANY) if sys.platform == "win32" else (cv2.CAP_ANY,)
        self._worker = threading.Thread(target=self._run, name="gatekeeper-camera", daemon=True)

    def start(self):
        self._worker.start()

    def stop(self):
        self._stop.set()
        with self._lock:
            self._latest = None

    def join(self, timeout=None):
        self._worker.join(timeout)

    def is_alive(self):
        return self._worker.is_alive()

    @property
    def generation(self):
        with self._lock:
            return self._generation

    @property
    def index(self):
        with self._lock:
            return self._index

    @property
    def available(self):
        with self._lock:
            return dict(self._available)

    def select(self, index):
        with self._lock:
            self._index = index
            self._generation += 1
            self._latest = None

    def snapshot(self, max_age=1.0):
        with self._lock:
            latest = self._latest
            if self._stop.is_set() or latest is None or time.monotonic() - latest.captured_at > max_age:
                return None
            return latest

    @property
    def discovering(self):
        with self._lock:
            return self._discovering

    def request_discovery(self):
        with self._lock:
            if self._discovering or self._stop.is_set():
                return
            self._discovering = True
            self._generation += 1
            self._latest = None
        self._search_requested.set()

    def _open(self, index, backends):
        for backend in backends:
            if self._stop.is_set():
                break
            cap = None
            ready = False
            try:
                cap = cv2.VideoCapture(index, backend)
                if not cap.isOpened():
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                # Some drivers need a couple of reads to deliver their first
                # frame. This does not impose an unsupported native timeout.
                for attempt in range(3):
                    ok, frame = cap.read()
                    if ok and frame is not None and frame.size:
                        ready = True
                        return cap, frame, backend
                    if self._stop.wait(0.03):
                        break
            except cv2.error:
                continue
            finally:
                if cap is not None and not ready:
                    cap.release()
        return None, None, None

    def _connect(self, index, generation, allow_fallback):
        # Fast path: open the selected camera ONCE and keep that same handle.
        cap, frame, backend = self._open(index, self._backends)
        selected = index
        if cap is None and allow_fallback:
            # Only search when the selected camera failed. Stop immediately at
            # the first usable camera instead of opening all remaining slots.
            for api in self._backends:
                for candidate in range(6):
                    if candidate == index or self._stop.is_set():
                        continue
                    cap, frame, backend = self._open(candidate, (api,))
                    if cap is not None:
                        selected = candidate
                        break
                if cap is not None or self._stop.is_set():
                    break
        with self._lock:
            if generation != self._generation or self._stop.is_set():
                stale = True
            else:
                stale = False
                if cap is not None:
                    if selected != index:
                        self._index = selected
                        self._generation += 1
                    self._available[selected] = f"Camera {selected}"
                generation = self._generation
        if stale and cap is not None:
            cap.release()
            cap = None
        return cap, frame, backend if backend is not None else self._backends[0], selected, generation

    def _discover(self, active_index, backend):
        # Explicit user search only. Skip the active handle; it is never
        # closed/reopened just to populate the dropdown.
        found = {active_index: f"Camera {active_index}"} if active_index is not None else {}
        generation = self.generation
        for index in range(6):
            if self._stop.is_set() or generation != self.generation:
                break
            if index == active_index:
                continue
            cap = None
            try:
                cap = cv2.VideoCapture(index, backend)
                if cap.isOpened():
                    found[index] = f"Camera {index}"
            except cv2.error:
                continue
            finally:
                if cap is not None:
                    cap.release()
        with self._lock:
            if generation == self._generation and found:
                self._available = found
            self._discovering = False

    def _publish(self, frame, generation):
        # Recognition receives raw orientation; only the UI preview is mirrored.
        frame = frame.copy()
        frame.flags.writeable = False
        with self._lock:
            if generation == self._generation and not self._stop.is_set():
                self._sequence += 1
                self._latest = CameraFrame(generation, self._sequence, time.monotonic(), frame)

    def _run(self):
        cap = None
        opened_generation = None
        opened_index = None
        backend = self._backends[0]
        fallback_after = 0.0
        try:
            while not self._stop.is_set():
                with self._lock:
                    index, generation = self._index, self._generation
                if self._search_requested.is_set():
                    self._search_requested.clear()
                    self._discover(opened_index if cap is not None else None, backend)
                    if cap is not None and opened_index == self.index:
                        opened_generation = self.generation
                    fallback_after = 0.0
                    continue
                if cap is None or generation != opened_generation:
                    if cap is not None:
                        cap.release()
                    allow_fallback = time.monotonic() >= fallback_after
                    cap, frame, backend, opened_index, opened_generation = self._connect(index, generation, allow_fallback)
                    if cap is None:
                        if allow_fallback:
                            fallback_after = time.monotonic() + 5.0
                        self._stop.wait(0.5)
                        continue
                    self._publish(frame, opened_generation)
                    continue
                try:
                    ok, frame = cap.read()
                except cv2.error:
                    ok = False
                if not ok or frame is None or not frame.size:
                    with self._lock:
                        self._latest = None
                        self._generation += 1
                    cap.release()
                    cap = None
                    self._stop.wait(0.5)
                    continue
                self._publish(frame, opened_generation)
        finally:
            if cap is not None:
                cap.release()
            with self._lock:
                self._latest = None
                self._discovering = False
