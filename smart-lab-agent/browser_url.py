"""Read Chrome/Edge address bars through Windows' built-in UI Automation.

The isolated, hidden PowerShell helper is persistent and killable if a browser
provider hangs. No extension, keyboard shortcuts, clipboard or browsing history.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import psutil
from program_identity import read_executable_identity
from domain_normalization import normalize_domain


def browser_name(identity):
    original = str((identity or {}).get("original_filename") or "").casefold()
    return {"chrome.exe": "Chrome", "msedge.exe": "Edge"}.get(original)


def foreground_window():
    if os.name != "nt":
        return 0
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.GetForegroundWindow.restype = ctypes.c_void_p
    return api.GetForegroundWindow() or 0


def window_process(window):
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    pid = ctypes.c_ulong()
    api.GetWindowThreadProcessId(window, ctypes.byref(pid))
    return psutil.Process(pid.value)


# Traverse browser chrome only: never descend into the webpage's Document tree.
# Ctrl+L is an exposed accessibility property, NOT a keystroke sent to the user.
UIA_HELPER = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
while ($line = [Console]::ReadLine()) {
    $value = $null
    try {
        $request = $line | ConvertFrom-Json
        $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr][long]$request.hwnd)
        if ($root.Current.ProcessId -ne [int]$request.pid) { throw 'Window changed' }
        $queue = New-Object System.Collections.Queue
        $queue.Enqueue(@($root, 0))
        $visited = 0
        while ($queue.Count -gt 0 -and $visited -lt 250) {
            $entry = $queue.Dequeue()
            $node = $entry[0]
            $depth = [int]$entry[1]
            $visited++
            $current = $node.Current
            if ($current.ControlType -eq [System.Windows.Automation.ControlType]::Document) { continue }
            if ($current.ControlType -eq [System.Windows.Automation.ControlType]::Edit) {
                $shortcut = ($current.AcceleratorKey -replace '\s', '').ToLowerInvariant()
                $isAddress = ($shortcut -eq 'ctrl+l' -or $shortcut -eq 'alt+d' -or
                              $current.AutomationId -eq 'addressEditBox')
                if ($isAddress -and -not $current.HasKeyboardFocus -and -not $current.IsOffscreen) {
                    $pattern = $node.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                    $value = [string]$pattern.Current.Value
                    break
                }
            }
            if ($depth -ge 8) { continue }
            $child = $walker.GetFirstChild($node)
            while ($null -ne $child -and $queue.Count -lt 250) {
                $queue.Enqueue(@($child, ($depth + 1)))
                $child = $walker.GetNextSibling($child)
            }
        }
    } catch { $value = $null }
    [Console]::WriteLine((ConvertTo-Json -InputObject @{ value = $value } -Compress))
}
'''


class BrowserURLReader:
    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self._closed = False

    def read(self, window, expected_pid=None):
        if os.name != "nt" or not window:
            return None
        try:
            process = window_process(window)
            if expected_pid is not None and process.pid != expected_pid:
                return None
            path = process.exe()
            identity = read_executable_identity(path)
            if not browser_name(identity):
                return None
            with self._lock:
                if self._closed:
                    return None
                if self._process is None or self._process.poll() is not None:
                    powershell = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                              "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
                    self._process = subprocess.Popen(
                        [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-MTA",
                         "-Command", UIA_HELPER],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                helper = self._process
                timer = threading.Timer(3, helper.kill)
                timer.daemon = True
                timer.start()
                try:
                    helper.stdin.write(json.dumps({"hwnd": window, "pid": process.pid}) + "\n")
                    helper.stdin.flush()
                    response = json.loads(helper.stdout.readline())
                finally:
                    timer.cancel()
            domain = normalize_domain(response.get("value"))
            if not domain or window_process(window).pid != process.pid:
                return None
            return {"domain": domain, "hwnd": window, "pid": process.pid,
                    "process_name": process.name(), "exe_path": path,
                    "executable_identity": identity}
        except (OSError, ValueError, psutil.Error, TypeError):
            return None

    def close(self):
        with self._lock:
            self._closed = True
            if self._process is not None:
                if self._process.poll() is None:
                    self._process.kill()
                self._process.wait(timeout=3)
                self._process.stdin.close()
                self._process.stdout.close()
                self._process = None


class BrowserURLMonitor:
    """One bounded worker; never queue repeated requests or block the Qt timer."""
    def __init__(self):
        self.reader = BrowserURLReader()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser-url")
        self.pending = None
        self.requested_at = 0
        self.closed = False

    def poll(self):
        window = foreground_window()
        result = None
        if self.pending is not None and self.pending.done():
            result = self.pending.result()
            self.pending = None
            if result and (result["hwnd"] != window or time.monotonic() - self.requested_at > 7):
                result = None
        if not self.closed and self.pending is None and window:
            self.requested_at = time.monotonic()
            self.pending = self.executor.submit(self.reader.read, window)
        return result

    def recheck(self, context):
        # A warning owns foreground focus: re-read the original browser window,
        # not a stale cached domain and not the warning dialog's title.
        try:
            return self.executor.submit(self.reader.read, context["browser_hwnd"],
                                        context["browser_pid"]).result(timeout=4)
        except (TimeoutError, KeyError, RuntimeError):
            return None

    def close(self):
        self.closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)
        # Cleanup is queued after any in-flight read instead of blocking Qt.
        threading.Thread(target=self.reader.close, daemon=True).start()
