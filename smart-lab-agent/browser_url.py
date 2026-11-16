"""Read browser address bars through Windows' built-in UI Automation.

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


def browser_name(identity, executable_path=None, process_name=None):
    identity = identity if isinstance(identity, dict) else {}
    executable_names = {
        "chrome.exe": "Chrome",
        "chromium.exe": "Chromium",
        "msedge.exe": "Edge",
        "safari.exe": "Safari",
        "iexplore.exe": "Internet Explorer",
        "firefox.exe": "Firefox",
        "brave.exe": "Brave",
        "opera.exe": "Opera",
        "opera_gx.exe": "Opera GX",
        "vivaldi.exe": "Vivaldi",
        "arc.exe": "Arc",
        "thorium.exe": "Thorium",
        "librewolf.exe": "LibreWolf",
        "waterfox.exe": "Waterfox",
        "floorp.exe": "Floorp",
        "palemoon.exe": "Pale Moon",
        "maxthon.exe": "Maxthon",
        "360chrome.exe": "360 Browser",
        "qqbrowser.exe": "QQ Browser",
        "baidubrowser.exe": "Baidu Browser",
        "duckduckgo.exe": "DuckDuckGo",
        "coccoc.exe": "Coc Coc",
        "coccoc_browser.exe": "Coc Coc",
        "yandex.exe": "Yandex Browser",
        "iridium.exe": "Iridium",
    }
    executable_candidates = [
        identity.get("original_filename"),
        identity.get("internal_name"),
        executable_path,
        process_name,
    ]
    for value in executable_candidates:
        executable = str(value or "").strip().replace("/", "\\").rsplit("\\", 1)[-1].casefold()
        if executable and not executable.endswith(".exe"):
            executable += ".exe"
        if executable in executable_names:
            return executable_names[executable]

    product = str(identity.get("product_name") or "").strip().casefold()
    if any(marker in product for marker in ("webview", "runtime", "embedded", "cef")):
        return None
    product_names = (
        ("google chrome", "Chrome"),
        ("chromium", "Chromium"),
        ("microsoft edge", "Edge"),
        ("firefox", "Firefox"),
        ("brave", "Brave"),
        ("opera gx", "Opera GX"),
        ("opera", "Opera"),
        ("vivaldi", "Vivaldi"),
        ("arc browser", "Arc"),
        ("thorium", "Thorium"),
        ("librewolf", "LibreWolf"),
        ("waterfox", "Waterfox"),
        ("floorp", "Floorp"),
        ("pale moon", "Pale Moon"),
        ("maxthon", "Maxthon"),
        ("360 browser", "360 Browser"),
        ("qq browser", "QQ Browser"),
        ("baidu browser", "Baidu Browser"),
        ("duckduckgo", "DuckDuckGo"),
        ("cốc cốc", "Coc Coc"),
        ("coc coc", "Coc Coc"),
        ("iridium", "Iridium"),
        ("yandex browser", "Yandex Browser"),
        ("safari", "Safari"),
        ("internet explorer", "Internet Explorer"),
    )
    for product_fragment, name in product_names:
        if product_fragment in product:
            return name
    if "browser" in product or "web browser" in product:
        return str(identity.get("product_name")).strip()
    return None


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


def is_browser_window(window):
    if os.name != "nt" or not window:
        return False
    api = ctypes.WinDLL("user32", use_last_error=True)
    get_class_name = api.GetClassNameW
    get_class_name.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    get_class_name.restype = ctypes.c_int
    class_name = ctypes.create_unicode_buffer(256)
    if not get_class_name(window, class_name, len(class_name)):
        return False
    return class_name.value.casefold() in {
        "chrome_widgetwin_1",
        "mozillawindowclass",
        "operawindowclass",
        "vivaldimainwindow",
    }


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
        while ($queue.Count -gt 0 -and $visited -lt 400) {
            $entry = $queue.Dequeue()
            $node = $entry[0]
            $depth = [int]$entry[1]
            $visited++
            try {
                $current = $node.Current
                if ($current.ControlType -eq [System.Windows.Automation.ControlType]::Document) { continue }
                if ($current.ControlType -eq [System.Windows.Automation.ControlType]::Edit -or
                    $current.ControlType -eq [System.Windows.Automation.ControlType]::ComboBox) {
                    $shortcut = ($current.AcceleratorKey -replace '\s', '').ToLowerInvariant()
                    $automationId = [string]$current.AutomationId
                    $name = [string]$current.Name
                    $isAddress = (
                        $shortcut -eq 'ctrl+l' -or $shortcut -eq 'alt+d' -or
                        $automationId -in @(
                            'addressEditBox', 'omnibox', 'urlbar-input', 'urlbar',
                            'addressbar-edit', 'addressfield', 'url-bar', 'urlbartextbox',
                            'urlbar-container', 'webkit-address-bar', 'location-bar', 'url-entry'
                        ) -or
                        $name -match '(?i)^(address( and search)? bar|address field|url bar|web address|search with .+ or enter (web )?address|search or enter (an? )?(web )?(address|url)|search and address bar)$'
                    )
                    if ($isAddress -and -not $current.HasKeyboardFocus -and -not $current.IsOffscreen) {
                        # Some browser versions expose multiple matching controls,
                        # and not every one supports ValuePattern. Skip those and
                        # continue searching instead of aborting the whole scan.
                        try {
                            $pattern = $node.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                            $candidate = [string]$pattern.Current.Value
                            if (-not [string]::IsNullOrWhiteSpace($candidate)) {
                                $value = $candidate
                                break
                            }
                        } catch { }
                    }
                }
                if ($depth -ge 10) { continue }
                $child = $walker.GetFirstChild($node)
                while ($null -ne $child -and $queue.Count -lt 400) {
                    $queue.Enqueue(@($child, ($depth + 1)))
                    $child = $walker.GetNextSibling($child)
                }
            } catch {
                # Browser UIA trees can change between individual reads. A stale
                # control must not discard valid address-bar siblings.
                continue
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
            if not browser_name(identity, path, process.name()) and not is_browser_window(window):
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
                timer = threading.Timer(4, helper.kill)
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
            completed = self.pending
            self.pending = None
            try:
                result = completed.result()
            except Exception:
                # Discard a failed read and keep polling on the next tick.
                result = None
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
