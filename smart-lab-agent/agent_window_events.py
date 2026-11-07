"""Track top-level window visibility transitions on Windows."""

import ctypes
import threading
from ctypes import wintypes


EVENT_OBJECT_DESTROY = 0x8001
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_HIDE = 0x8003
OBJID_WINDOW = 0
CHILDID_SELF = 0
WINEVENT_OUTOFCONTEXT = 0


class WindowVisibilityTracker:
    """Remember visible HWNDs and report when a process becomes visible again."""

    def __init__(self):
        self._windows_by_pid = {}
        self._shown_process_ids = set()
        self._lock = threading.Lock()

    def seed_visible_window(self, hwnd, process_id):
        if not hwnd or not process_id:
            return
        with self._lock:
            self._windows_by_pid.setdefault(int(process_id), set()).add(int(hwnd))

    def handle_event(self, event_id, hwnd, process_id, object_id=OBJID_WINDOW, child_id=CHILDID_SELF):
        if (
            not hwnd
            or object_id != OBJID_WINDOW
            or child_id != CHILDID_SELF
        ):
            return

        hwnd = int(hwnd)
        with self._lock:
            if event_id == EVENT_OBJECT_SHOW:
                if not process_id:
                    return
                process_id = int(process_id)
                windows = self._windows_by_pid.setdefault(process_id, set())
                was_hidden = not windows
                windows.add(hwnd)
                if was_hidden:
                    self._shown_process_ids.add(process_id)
            elif event_id in (EVENT_OBJECT_HIDE, EVENT_OBJECT_DESTROY):
                process_ids = [
                    pid for pid, windows in self._windows_by_pid.items() if hwnd in windows
                ]
                for target_pid in process_ids:
                    windows = self._windows_by_pid.get(target_pid)
                    if windows:
                        windows.discard(hwnd)
                        if not windows:
                            self._windows_by_pid.pop(target_pid, None)

    def consume_shown_process_ids(self):
        with self._lock:
            process_ids = self._shown_process_ids
            self._shown_process_ids = set()
            return process_ids

    def prune(self, running_process_ids):
        running_process_ids = set(running_process_ids)
        with self._lock:
            self._windows_by_pid = {
                process_id: windows
                for process_id, windows in self._windows_by_pid.items()
                if process_id in running_process_ids
            }
            self._shown_process_ids.intersection_update(running_process_ids)


class WindowVisibilityMonitor:
    """Use SetWinEventHook so hide/show cycles between polling ticks are retained."""

    def __init__(self, ignored_process_id=None):
        if not hasattr(ctypes, "windll") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("Windows accessibility events are unavailable")

        self._user32 = ctypes.windll.user32
        self._tracker = WindowVisibilityTracker()
        self._ignored_process_id = ignored_process_id
        self._callback_type = ctypes.WINFUNCTYPE(
            None,
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.HWND,
            wintypes.LONG,
            wintypes.LONG,
            wintypes.DWORD,
            wintypes.DWORD,
        )
        self._callback = self._callback_type(self._on_event)

        set_hook = self._user32.SetWinEventHook
        set_hook.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HMODULE,
            self._callback_type,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        set_hook.restype = wintypes.HANDLE
        self._user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        self._user32.UnhookWinEvent.restype = wintypes.BOOL
        self._user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        self._hook = set_hook(
            EVENT_OBJECT_DESTROY,
            EVENT_OBJECT_HIDE,
            None,
            self._callback,
            0,
            0,
            WINEVENT_OUTOFCONTEXT,
        )
        if not self._hook:
            raise OSError(ctypes.get_last_error(), "SetWinEventHook failed")
        self._seed_visible_windows()

    def _process_id_for_window(self, hwnd):
        process_id = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        return process_id.value or None

    def _seed_visible_windows(self):
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        is_visible = self._user32.IsWindowVisible
        is_visible.argtypes = [wintypes.HWND]
        is_visible.restype = wintypes.BOOL

        def seed(hwnd, _parameter):
            if is_visible(hwnd):
                process_id = self._process_id_for_window(hwnd)
                if process_id != self._ignored_process_id:
                    self._tracker.seed_visible_window(hwnd, process_id)
            return True

        callback = callback_type(seed)
        self._user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        self._user32.EnumWindows.restype = wintypes.BOOL
        self._user32.EnumWindows(callback, 0)

    def _on_event(self, _hook, event_id, hwnd, object_id, child_id, _thread_id, _event_time):
        process_id = self._process_id_for_window(hwnd)
        if process_id == self._ignored_process_id:
            return
        self._tracker.handle_event(event_id, hwnd, process_id, object_id, child_id)

    def consume_shown_process_ids(self):
        return self._tracker.consume_shown_process_ids()

    def prune(self, running_process_ids):
        self._tracker.prune(running_process_ids)

    def close(self):
        hook = getattr(self, "_hook", None)
        if hook:
            self._user32.UnhookWinEvent(hook)
            self._hook = None
        self._callback = None
