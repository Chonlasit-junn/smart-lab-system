import sys
import os
import ctypes
import psutil
import json
import socket
import threading
import uuid
import time
import requests
import pygetwindow as gw
from datetime import datetime, timezone
from types import SimpleNamespace
from agent_device import get_agent_data_dir, load_device_registration
from agent_outbox import AgentOutbox
from program_identity import program_usage_name, read_executable_identity
from browser_url import BrowserURLMonitor
from agent_policy import (
    DEFAULT_FALLBACK_RULES,
    find_process_match,
    find_website_match,
    normalize_rules,
)
from agent_violation import (
    DEFAULT_GRACE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_WARNING_SECONDS,
    ViolationState,
)
from agent_cleanup import SessionCleanupManager
from agent_window_events import WindowVisibilityMonitor
from qt_runtime import prepare_qt_dll_search_path


def _utc_now():
    """Return an aware UTC timestamp for events sent to the Backend."""

    return datetime.now(timezone.utc)


def _append_monitor_error_log(error_type):
    """Persist a small, local-only diagnostic without recording app or user data."""
    try:
        log_path = get_agent_data_dir() / "monitor-errors.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if log_path.exists() and log_path.stat().st_size > 64 * 1024:
            log_path.write_text("", encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{_utc_now().isoformat(timespec='seconds')} {error_type}\n")
    except OSError:
        # Diagnostics must never interrupt monitoring or session shutdown.
        pass


prepare_qt_dll_search_path()

from agent_background import BackgroundTaskRunner
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QFrame,
                             QGraphicsDropShadowEffect, QMessageBox, QDialog)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont, QColor

# Hugging Face Space อาจ sleep อยู่ — retry ให้อัตโนมัติ
def post_with_retry(url, data=None, json_data=None, headers=None, retries=3, timeout=15):
    for attempt in range(retries):
        try:
            if json_data is not None:
                return requests.post(url, json=json_data, headers=headers, timeout=timeout)
            return requests.post(url, data=data, headers=headers, timeout=timeout)
        except requests.exceptions.ConnectionError:
            if attempt < retries - 1:
                time.sleep(3)
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(2)
    return None


def response_detail(response):
    """Return a safe API detail without exposing a raw response body."""
    if response is None:
        return ""
    try:
        payload = response.json()
    except (ValueError, AttributeError):
        return ""
    if isinstance(payload, dict):
        return str(payload.get("detail", ""))
    return ""


def _with_device_credentials(payload):
    return {
        **payload,
        "device_id": REGISTERED_DEVICE_ID or None,
        "device_token": DEVICE_TOKEN or None,
    }


def _session_auth_headers(agent):
    token = str(getattr(agent, "current_access_token", "") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else None


def _window_process_id(window):
    """Resolve the current owner of an HWND, including on 64-bit Windows."""
    handle = getattr(window, "_hWnd", None)
    user32 = getattr(getattr(ctypes, "windll", None), "user32", None)
    if not handle or user32 is None:
        return None
    process_id = ctypes.c_ulong()
    try:
        get_process_id = user32.GetWindowThreadProcessId
        get_process_id.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        get_process_id.restype = ctypes.c_ulong
        get_process_id(int(handle), ctypes.byref(process_id))
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    return process_id.value or None


def _visible_window_handles_by_pid():
    """Return visible top-level HWNDs grouped by their owning process."""
    user32 = getattr(getattr(ctypes, "windll", None), "user32", None)
    callback_factory = getattr(ctypes, "WINFUNCTYPE", None)
    if user32 is None or callback_factory is None:
        return {}

    windows_by_pid = {}
    try:
        is_window_visible = user32.IsWindowVisible
        is_window_visible.argtypes = [ctypes.c_void_p]
        is_window_visible.restype = ctypes.c_int
        get_window_process_id = user32.GetWindowThreadProcessId
        get_window_process_id.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        get_window_process_id.restype = ctypes.c_ulong
        enum_windows = user32.EnumWindows
        callback_type = callback_factory(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

        def collect_visible_process(hwnd, _parameter):
            if not is_window_visible(hwnd):
                return True
            process_id = ctypes.c_ulong()
            get_window_process_id(hwnd, ctypes.byref(process_id))
            if process_id.value:
                handle = hwnd.value if hasattr(hwnd, "value") else hwnd
                windows_by_pid.setdefault(process_id.value, set()).add(int(handle))
            return True

        callback = callback_type(collect_visible_process)
        enum_windows.argtypes = [callback_type, ctypes.c_void_p]
        enum_windows.restype = ctypes.c_int
        enum_windows(callback, None)
    except (AttributeError, OSError, TypeError, ValueError):
        return {}
    return windows_by_pid


def _visible_window_process_ids():
    """Return PIDs that currently own a visible top-level Windows window."""
    return set(_visible_window_handles_by_pid())


def _is_agent_window(window, process_id=None):
    """Check ownership independently of the window title or EXE filename."""
    if process_id is None:
        process_id = _window_process_id(window)
    return process_id == os.getpid()


def _window_class_name(window):
    handle = getattr(window, "_hWnd", None)
    user32 = getattr(getattr(ctypes, "windll", None), "user32", None)
    if not handle or user32 is None:
        return ""
    try:
        get_class_name = user32.GetClassNameW
        get_class_name.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        get_class_name.restype = ctypes.c_int
        name = ctypes.create_unicode_buffer(256)
        get_class_name(int(handle), name, len(name))
        return name.value
    except (AttributeError, OSError, TypeError, ValueError):
        return ""


def _usage_name_for_window(window, process_id=None):
    process_id = process_id or _window_process_id(window)
    if not process_id or _is_agent_window(window, process_id):
        return None
    try:
        process = psutil.Process(process_id)
        try:
            exe_path = process.exe()
        except psutil.AccessDenied:
            exe_path = None
        # exe() gives the full image name; only query name() as a fallback.
        process_name = process.name() if not exe_path else ""
        identity = read_executable_identity(exe_path) if exe_path else {}
        name = program_usage_name(process_name, exe_path, identity)
        # Explorer also owns the desktop/taskbar. Keep those excluded without
        # excluding real File Explorer windows or relying on localized titles.
        if name == "explorer.exe" and _window_class_name(window) in {
            "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
        }:
            return None
        return name
    except (psutil.Error, OSError, AttributeError, TypeError, ValueError):
        return None


# ── CONFIG ────────────────────────────────────────────────────────────────────
DEFAULT_API_URL = "https://h0sh1na-smart-lab-backend.hf.space"
USAGE_LOG_BATCH_SIZE = 100
DEVICE_REGISTRATION = load_device_registration() or {}
API_URL = os.getenv(
    "SMART_LAB_API_URL",
    str(DEVICE_REGISTRATION.get("api_url") or DEFAULT_API_URL),
).rstrip("/")
REGISTERED_DEVICE_ID = str(DEVICE_REGISTRATION.get("device_id") or "").strip()
DEVICE_TOKEN = str(DEVICE_REGISTRATION.get("device_token") or "").strip()
LAB_CODE   = str(
    DEVICE_REGISTRATION.get("lab_code")
    or os.getenv("SMART_LAB_CODE", "LAB01")
).strip()
AGENT_VERSION = os.getenv("SMART_LAB_AGENT_VERSION", "source")
DEBUG_MODE = os.getenv("SMART_LAB_AGENT_DEBUG", "1").strip().lower() in {"1", "true", "yes", "on"}
# Keep workstation cleanup opt-in while it is being validated on Lab machines.
# Set SMART_LAB_SESSION_CLEANUP=1 explicitly when this feature is ready.
_cleanup_default = "0"
SESSION_CLEANUP_ENABLED = os.getenv(
    "SMART_LAB_SESSION_CLEANUP",
    _cleanup_default,
).strip().lower() in {"1", "true", "yes", "on"}
DEVICE_NAME = socket.gethostname()
DEVICE_MAC  = ':'.join(f'{byte:02x}' for byte in uuid.getnode().to_bytes(6, 'big'))

try:
    POLICY_REFRESH_SECONDS = max(
        30,
        int(os.getenv("SMART_LAB_POLICY_REFRESH_SECONDS", "60")),
    )
except ValueError:
    POLICY_REFRESH_SECONDS = 60

IGNORE_SYSTEM_APPS = {
    "systemsettings.exe", "searchhost.exe", "searchapp.exe",
    "searchui.exe", "lockapp.exe",
}
USAGE_CHECKPOINT_SECONDS = 30


# ── Violation Dialog ──────────────────────────────────────────────────────────
class ViolationDialog(QDialog):
    def __init__(
        self,
        reason,
        *,
        attempt=DEFAULT_MAX_ATTEMPTS,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        allow_grace=False,
        warning_seconds=DEFAULT_WARNING_SECONDS,
        grace_seconds=DEFAULT_GRACE_SECONDS,
        parent=None,
    ):
        super().__init__(parent)
        self.allow_grace = bool(allow_grace)
        self.left = max(1, int(warning_seconds))
        self.grace_minutes = (max(1, int(grace_seconds)) + 59) // 60
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog
        )
        self.setStyleSheet("""
            QDialog { background-color: #fef2f2; border: 3px solid #ef4444; border-radius: 15px; }
            QLabel  { border: none; }
        """)
        self.setFixedSize(600, 380 if self.allow_grace else 260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(10)

        title = QLabel(
            "⚠️ ตรวจพบการใช้งานที่ไม่อนุญาต"
            if self.allow_grace
            else "🚫 หมดสิทธิ์ขอโอกาส"
        )
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        title.setStyleSheet("color: #dc2626;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        reason_lbl = QLabel(f"สาเหตุ: {reason}")
        reason_lbl.setFont(QFont("Segoe UI", 14))
        reason_lbl.setStyleSheet("color: #7f1d1d; margin-top: 10px;")
        reason_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reason_lbl.setWordWrap(True)

        attempt_lbl = QLabel(
            f"การเตือนครั้งที่ {attempt} จาก {max_attempts}"
            if self.allow_grace
            else f"ตรวจพบซ้ำครบครั้งที่ {attempt} จาก {max_attempts}"
        )
        attempt_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        attempt_lbl.setStyleSheet("color: #7f1d1d;")
        attempt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.countdown_lbl = QLabel()
        self.countdown_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.countdown_lbl.setStyleSheet("color: #ef4444; margin-top: 20px;")
        self.countdown_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_lbl.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(reason_lbl)
        layout.addWidget(attempt_lbl)
        layout.addWidget(self.countdown_lbl)

        if self.allow_grace:
            self._update_countdown_text()
            chance_btn = QPushButton("ขอโอกาส")
            chance_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            chance_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f59e0b; color: white; border-radius: 8px;
                    font-family: 'Segoe UI'; font-size: 14px; font-weight: bold;
                    padding: 11px; border: none;
                }
                QPushButton:hover { background-color: #fbbf24; }
                QPushButton:pressed { background-color: #d97706; }
            """)
            chance_btn.clicked.connect(self.accept)
            layout.addWidget(chance_btn)
        else:
            self.countdown_lbl.setText(
                f"ระบบจะปิด Session ใน {self.left} วินาที..."
            )

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

        # center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())

    def _tick(self):
        self.left -= 1
        if self.allow_grace:
            self._update_countdown_text()
        else:
            self.countdown_lbl.setText(f"ระบบจะปิด Session ใน {self.left} วินาที...")
        if self.left <= 0:
            self.timer.stop()
            if self.allow_grace:
                self.reject()
            else:
                self.accept()

    def _update_countdown_text(self):
        self.countdown_lbl.setText(
            f"หากขอโอกาส จะมีเวลา {self.grace_minutes} นาทีเพื่อปิดโปรแกรม/เว็บไซต์ "
            f"หากยังเปิดอยู่ระบบจะแจ้งเตือนอีกครั้ง\nเลือกภายใน {self.left} วินาที"
        )


# ── SessionInfoBar ────────────────────────────────────────────────────────────
class SessionInfoBar(QWidget):
    def __init__(self, email, overlay, session_id):
        super().__init__()
        self.email      = email
        self.overlay    = overlay
        self.session_id = session_id
        self._init_ui()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._expanded = False
        self._compact_size = (56, 56)
        self._expanded_size = (340, 150)
        self.setFixedSize(*self._compact_size)
        self._position_on_screen()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        self.container = QFrame()
        self.container.setFixedSize(
            self._compact_size[0] - 8,
            self._compact_size[1] - 8,
        )
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(15, 23, 42, 230);
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setYOffset(5)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.container.setGraphicsEffect(shadow)

        inner = QVBoxLayout(self.container)
        inner.setContentsMargins(6, 6, 6, 6)
        inner.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.status_label = QLabel("●  กำลังตรวจสอบ")
        self.status_label.setStyleSheet(
            "color: #22c55e; font-family: 'Segoe UI'; font-size: 12px; font-weight: bold; border: none; background: transparent;"
        )
        self.status_label.hide()
        header.addWidget(self.status_label, 1)

        self.toggle_btn = QPushButton("⌄")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setFixedSize(28, 28)
        self.toggle_btn.setToolTip("เปิดรายละเอียด Session")
        self.toggle_btn.setStyleSheet(
            "QPushButton { color: #cbd5e1; background: rgba(255,255,255,18); "
            "border: none; border-radius: 8px; font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { background: rgba(255,255,255,35); }"
        )
        self.toggle_btn.clicked.connect(self._toggle_expanded)
        header.addWidget(self.toggle_btn)
        inner.addLayout(header)

        self.details_widget = QWidget()
        details = QVBoxLayout(self.details_widget)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(6)

        self.user_label = QLabel(f"👤  {self.email}")
        self.user_label.setWordWrap(True)
        self.user_label.setStyleSheet(
            "color: #cbd5e1; font-family: 'Segoe UI'; font-size: 12px; border: none; background: transparent;"
        )

        self.logout_btn = QPushButton("จบการทำงาน")
        self.logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_btn.setFixedHeight(40)
        self.logout_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444; color: white; border-radius: 8px;
                font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
                padding: 8px; border: none; margin-top: 4px;
            }
            QPushButton:hover   { background-color: #f87171; }
            QPushButton:pressed { background-color: #b91c1c; }
        """)
        self.logout_btn.clicked.connect(self._confirm_logout)

        details.addWidget(self.user_label)
        details.addWidget(self.logout_btn)
        self.details_widget.hide()
        inner.addWidget(self.details_widget)
        outer.addWidget(self.container)

    def _position_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.move(geometry.x() + geometry.width() - self.width() - 12, geometry.y() + 12)

    def _toggle_expanded(self):
        self._expanded = not self._expanded
        self.details_widget.setVisible(self._expanded)
        self.status_label.setVisible(self._expanded)
        self.toggle_btn.setText("⌃" if self._expanded else "⌄")
        self.toggle_btn.setToolTip(
            "ซ่อนรายละเอียด Session" if self._expanded else "เปิดรายละเอียด Session"
        )
        size = self._expanded_size if self._expanded else self._compact_size
        self.container.setFixedSize(size[0] - 8, size[1] - 8)
        self.setFixedSize(*size)
        self.layout().activate()
        self.container.layout().activate()
        self._position_on_screen()

    def _confirm_logout(self):
        # ใช้ QDialog() ไม่มี parent — Tool window เป็น parent ไม่ได้ dialog จะไม่รับ event
        dlg = QDialog()
        dlg.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint  |
            Qt.WindowType.Dialog
        )
        dlg.setFixedSize(360, 180)
        dlg.setStyleSheet("background-color: #1e293b; border-radius: 16px;")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        title = QLabel("จบการใช้งาน?")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color: #f1f5f9; font-family: 'Segoe UI'; font-size: 16px; font-weight: bold; border: none; background: transparent;"
        )

        sub = QLabel("ระบบจะบันทึกสถิติและล็อกเอาท์")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            "color: #64748b; font-family: 'Segoe UI'; font-size: 12px; border: none; background: transparent;"
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        cancel_btn = QPushButton("ยังอยู่ต่อ")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155; color: #cbd5e1; border-radius: 8px;
                font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
                padding: 10px; border: none;
            }
            QPushButton:hover { background-color: #475569; }
        """)
        cancel_btn.clicked.connect(dlg.reject)

        confirm_btn = QPushButton("ใช่ จบเลย")
        confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444; color: white; border-radius: 8px;
                font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
                padding: 10px; border: none;
            }
            QPushButton:hover { background-color: #f87171; }
        """)
        confirm_btn.clicked.connect(dlg.accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)

        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addStretch()
        layout.addLayout(btn_row)

        screen = QApplication.primaryScreen().geometry()
        dlg.move(screen.center() - dlg.rect().center())

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.trigger_logout()

    def trigger_logout(self, reason: str = None, show_dialog: bool = True):
        if reason and show_dialog:
            violation_state = getattr(self.overlay.agent, "violation_state", None)
            attempt = getattr(violation_state, "attempts", DEFAULT_MAX_ATTEMPTS)
            max_attempts = getattr(
                violation_state,
                "max_attempts",
                DEFAULT_MAX_ATTEMPTS,
            )
            dlg = ViolationDialog(
                reason,
                attempt=max(attempt, DEFAULT_MAX_ATTEMPTS),
                max_attempts=max_attempts,
                allow_grace=False,
            )
            dlg.exec()
        self.overlay.agent.stop_and_send_logs(
            self.session_id,
            end_reason="violation" if reason else "logout",
        )
        self.hide()
        self.overlay.reset_and_show()


# ── LoginOverlay ──────────────────────────────────────────────────────────────
class LoginOverlay(QWidget):
    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        self.agent.set_ui_references(self)
        self.is_authenticated = False
        self._init_ui()

        self.focus_timer = QTimer()
        self.focus_timer.timeout.connect(self._lock_focus)
        self.focus_timer.start(1000)

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setGeometry(QApplication.primaryScreen().geometry())
        self.setStyleSheet("background-color: #0f172a;")

        main = QVBoxLayout(self)
        main.addStretch()
        row = QHBoxLayout()
        row.addStretch()

        card = QFrame()
        card.setFixedSize(450, 580)
        card.setStyleSheet("background-color: #ffffff; border-radius: 25px;")

        cl = QVBoxLayout(card)
        cl.setContentsMargins(45, 45, 45, 45)

        title = QLabel("Smart Lab Access")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setStyleSheet("color: #1e293b; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(title)

        self.error_label = QLabel("")
        self.error_label.setFont(QFont("Segoe UI", 11))
        self.error_label.setStyleSheet(
            "color: #dc2626; background-color: #fee2e2; padding: 10px; border-radius: 8px; margin-top: 15px;"
        )
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        cl.addWidget(self.error_label)

        cl.addWidget(QLabel("Email", styleSheet="color: #475569; font-weight: bold; margin-top: 20px; border: none; font-family: 'Segoe UI';"))
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("name@bumail.net")
        self.email_input.setStyleSheet(self._input_style())
        self.email_input.returnPressed.connect(lambda: self.pass_input.setFocus())
        cl.addWidget(self.email_input)

        cl.addWidget(QLabel("Password", styleSheet="color: #475569; font-weight: bold; margin-top: 15px; border: none; font-family: 'Segoe UI';"))
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setStyleSheet(self._input_style())
        self.pass_input.returnPressed.connect(self.handle_login)  # Enter → login
        cl.addWidget(self.pass_input)

        self.login_btn = QPushButton("ปลดล็อกเข้าใช้งาน")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb; color: white; padding: 15px; border-radius: 10px;
                font-weight: bold; font-family: 'Segoe UI'; font-size: 15px; margin-top: 25px; border: none;
            }
            QPushButton:hover    { background-color: #1d4ed8; }
            QPushButton:disabled { background-color: #94a3b8; color: #f1f5f9; }
        """)
        self.login_btn.clicked.connect(self.handle_login)
        cl.addWidget(self.login_btn)

        row.addWidget(card)
        row.addStretch()
        main.addLayout(row)
        main.addStretch()

    def _input_style(self) -> str:
        return """
            QLineEdit {
                padding: 12px; border: 2px solid #e2e8f0; border-radius: 10px;
                font-size: 16px; color: #1e293b; background-color: #f8fafc; font-family: 'Segoe UI';
            }
            QLineEdit:focus { border: 2px solid #3b82f6; background-color: #ffffff; }
        """

    def _lock_focus(self):
        if not self.is_authenticated:
            if not self.isFullScreen():
                self.showFullScreen()
            self.raise_()
            self.activateWindow()

    def reset_and_show(self):
        self.is_authenticated = False
        self.email_input.clear()
        self.pass_input.clear()
        self.error_label.hide()
        self.login_btn.setText("ปลดล็อกเข้าใช้งาน")
        self.login_btn.setEnabled(True)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def _show_error(self, msg: str):
        self.error_label.setText(f"⚠️ {msg}")
        self.error_label.show()

    def handle_login(self):
        if not self.login_btn.isEnabled():
            return

        email    = self.email_input.text().strip()
        password = self.pass_input.text()

        if not email or not password:
            self._show_error("กรุณากรอกข้อมูลให้ครบถ้วน")
            return

        if not REGISTERED_DEVICE_ID or not DEVICE_TOKEN:
            self._show_error("เครื่องนี้ยังไม่ได้ลงทะเบียนกับ Lab กรุณาติดต่อผู้ดูแล")
            return

        self.error_label.hide()
        self.login_btn.setText("⏳ กำลังตรวจสอบ...")
        self.login_btn.setEnabled(False)
        submitted = self.agent.background_tasks.submit(
            "login",
            lambda: self._authenticate_and_start_session(email, password),
            self._handle_login_result,
        )
        if not submitted:
            self.login_btn.setText("ปลดล็อกเข้าใช้งาน")
            self.login_btn.setEnabled(True)
            self._show_error("กำลังตรวจสอบการเข้าสู่ระบบอยู่ กรุณารอสักครู่")

    def _authenticate_and_start_session(self, email, password):
        response = post_with_retry(
            f"{API_URL}/login",
            data={"username": email, "password": password},
        )
        if response is None:
            return {"kind": "connection_error"}
        if response.status_code == 429:
            return {"kind": "login_limited"}
        if response.status_code == 403:
            if response_detail(response) == "This account is not active.":
                return {"kind": "account_inactive"}
            return {"kind": "approval_required"}
        if response.status_code >= 500:
            return {"kind": "connection_error"}
        if response.status_code != 200:
            return {"kind": "invalid_credentials"}
        try:
            access_token = response.json().get("access_token")
        except (AttributeError, ValueError):
            access_token = None
        if not isinstance(access_token, str) or not access_token.strip():
            return {"kind": "invalid_credentials"}
        self.agent.current_access_token = access_token
        session_headers = {"Authorization": f"Bearer {access_token}"}

        # Deliver any prior session's durable requests before claiming this device.
        self.agent.flush_outbox(limit=5)
        client_session_id = self.agent.get_or_create_session_attempt(email)
        session_data = {
            "email": email,
            "lab_code": LAB_CODE,
            "device": DEVICE_NAME,
            "device_mac": DEVICE_MAC,
            "device_id": REGISTERED_DEVICE_ID or None,
            "device_token": DEVICE_TOKEN or None,
            "agent_version": AGENT_VERSION,
            "client_session_id": client_session_id,
        }
        session_response = post_with_retry(
            f"{API_URL}/agent/start-session",
            data=session_data,
            headers=session_headers,
        )

        # Retry once with a fresh idempotency key if the old request was closed.
        if session_response is not None and session_response.status_code == 409:
            detail = response_detail(session_response).lower()
            if "session request is already closed" in detail:
                self.agent.discard_session_attempt(client_session_id)
                client_session_id = self.agent.get_or_create_session_attempt(email)
                session_data["client_session_id"] = client_session_id
                session_response = post_with_retry(
                    f"{API_URL}/agent/start-session",
                    data=session_data,
                    headers=session_headers,
                )

        if (
            session_response is not None
            and session_response.status_code == 403
            and "booking" in response_detail(session_response).lower()
        ):
            return {"kind": "booking_required"}

        if session_response is not None and session_response.status_code == 403:
            kind = {
                "Your account is pending admin approval.": "approval_required",
                "This account is not active.": "account_inactive",
                "This account has an active ban.": "user_banned",
            }.get(response_detail(session_response))
            if kind:
                return {"kind": kind}

        if session_response is not None and session_response.status_code == 200:
            session_id = session_response.json().get("session_id")
            if session_id is not None:
                self.agent.confirm_session_attempt(client_session_id)
                return {
                    "kind": "success",
                    "session_id": session_id,
                    "email": email,
                }

        status = session_response.status_code if session_response is not None else None
        if status == 409:
            return {"kind": "active_session"}
        return {"kind": "session_error", "status": status}

    def _handle_login_result(self, result, error):
        try:
            if error is not None:
                print(f"เข้าสู่ระบบไม่สำเร็จ: {error}")
                self._show_error("เกิดข้อผิดพลาดในการเชื่อมต่อ กรุณาลองอีกครั้ง")
                return

            kind = result.get("kind") if isinstance(result, dict) else None
            if kind == "success":
                session_id = result["session_id"]
                self.is_authenticated = True
                self.hide()
                self.info_bar = SessionInfoBar(
                    result.get("email", self.email_input.text().strip()),
                    self,
                    session_id,
                )
                self.info_bar.show()
                self.agent.start_monitoring(session_id, self.info_bar)
            elif kind == "connection_error":
                self._show_error("ไม่สามารถเชื่อมต่อ Server ได้ กรุณาตรวจสอบอินเทอร์เน็ต")
            elif kind == "approval_required":
                self._show_error("บัญชีนี้รอการอนุมัติจาก Admin")
            elif kind == "account_inactive":
                self._show_error("บัญชีนี้ถูกปิดใช้งาน กรุณาติดต่อผู้ดูแล")
            elif kind == "user_banned":
                self._show_error("บัญชีนี้ถูกระงับการใช้ Lab ชั่วคราว กรุณาดูสถานะในหน้าโปรไฟล์")
            elif kind == "login_limited":
                self._show_error("เข้าสู่ระบบถี่เกินไป กรุณารอสักครู่แล้วลองใหม่")
            elif kind == "invalid_credentials":
                self._show_error("อีเมลหรือรหัสผ่านไม่ถูกต้อง")
            elif kind == "active_session":
                self._show_error("ผู้ใช้หรือเครื่องนี้มี Session ที่ยังไม่จบอยู่")
            elif kind == "booking_required":
                self._show_error("ไม่มีรายการจอง Lab ที่ใช้งานได้ในขณะนี้ กรุณาจองก่อนเข้าใช้งาน")
            else:
                self._show_error("ไม่สามารถสร้าง Session ใหม่ได้")
        finally:
            self.login_btn.setText("ปลดล็อกเข้าใช้งาน")
            self.login_btn.setEnabled(True)


# ── SmartLabAgent ─────────────────────────────────────────────────────────────
class SmartLabAgent:
    def __init__(self):
        self.background_tasks = BackgroundTaskRunner(max_threads=3)
        self._outbox_flush_lock = threading.Lock()
        self._outbox_state_lock = threading.Lock()
        self._pending_fallback_violations = []
        try:
            self.outbox = AgentOutbox()
            self._outbox_has_pending = bool(self.outbox.pending_count())
            print(f"Agent outbox: {self.outbox.path}")
        except Exception as e:
            # Keep the UI available, but make the degraded delivery mode
            # visible in the log instead of silently losing telemetry.
            self.outbox = None
            self._outbox_has_pending = False
            print(f"Agent outbox unavailable: {e}")

        self.usage_segments = []
        self.current_activity_name = None
        self.current_activity_started_at = None
        self.current_session_id = None
        self.current_access_token = None
        self.info_bar       = None
        self.overlay        = None
        self.policy_rules = []
        self.policy_version = None
        self.policy_source = None
        self.policy_token = None
        self.seen_process_ids = set()
        self.seen_visible_process_ids = set()
        self.seen_visible_window_handles_by_pid = {}
        self.pending_window_reopen_process_ids = set()
        self._process_scan_generation = 0
        self._process_scan_in_flight = False
        self._process_scan_pending_shown = {}
        self._usage_name_cache = {}
        self.window_visibility_monitor = None
        self._last_track_usage_error = None
        self.violation_reported = False
        self.violation_state = ViolationState()
        self.violation_grace_context = None
        self.violation_dialog_active = False
        self.session_cleanup = None
        self.monitor_timer  = QTimer()
        self.monitor_timer.timeout.connect(self.track_usage)
        self.heartbeat_timer = QTimer()
        self.heartbeat_timer.timeout.connect(self.send_heartbeat)
        self.policy_timer = QTimer()
        self.policy_timer.timeout.connect(self.refresh_policy)
        self.outbox_retry_timer = QTimer()
        self.outbox_retry_timer.timeout.connect(self.retry_outbox)
        self.outbox_retry_timer.start(30_000)
        QTimer.singleShot(0, self.retry_outbox)

    def get_or_create_session_attempt(self, email):
        if self.outbox is None:
            return uuid.uuid4().hex
        return self.outbox.get_or_create_session_attempt(
            email=email,
            lab_code=LAB_CODE,
            device=DEVICE_NAME,
            device_mac=DEVICE_MAC,
        )

    def confirm_session_attempt(self, client_session_id):
        if self.outbox is not None:
            self.outbox.clear_session_attempt(client_session_id)

    def discard_session_attempt(self, client_session_id):
        if self.outbox is not None:
            self.outbox.clear_session_attempt(client_session_id)

    def _queue_outbox(self, kind, payload, session_id=None, event_id=None):
        if self.outbox is None:
            return False
        try:
            state_lock = getattr(self, "_outbox_state_lock", None)
            if state_lock is None:
                self.outbox.enqueue(
                    kind=kind,
                    payload=payload,
                    session_id=session_id,
                    event_id=event_id,
                )
                self._outbox_has_pending = True
            else:
                with state_lock:
                    self.outbox.enqueue(
                        kind=kind,
                        payload=payload,
                        session_id=session_id,
                        event_id=event_id,
                    )
                    self._outbox_has_pending = True
            return True
        except Exception as e:
            print(f"บันทึกข้อมูลลง local outbox ไม่ได้: {e}")
            return False

    @staticmethod
    def _has_pending_outbox_hint(instance):
        state_lock = getattr(instance, "_outbox_state_lock", None)
        if state_lock is None:
            return getattr(instance, "_outbox_has_pending", True)
        with state_lock:
            return instance._outbox_has_pending

    def flush_outbox(self, limit=3):
        """Deliver queued telemetry and keep failed items for a later retry."""
        with self._outbox_flush_lock:
            return self._flush_outbox_locked(limit)

    def retry_outbox(self):
        """Retry durable telemetry in the background, including on the login screen."""
        if self.outbox is None or not SmartLabAgent._has_pending_outbox_hint(self):
            return False

        return self.background_tasks.submit(
            "outbox-retry",
            lambda: self.flush_outbox(limit=3),
            self._handle_outbox_retry,
        )

    @staticmethod
    def _handle_outbox_retry(_sent, error):
        if error is not None:
            print(f"ส่งข้อมูลจาก local outbox ไม่สำเร็จ: {error}")

    def _flush_outbox_locked(self, limit=3):
        if self.outbox is None or not SmartLabAgent._has_pending_outbox_hint(self):
            return 0

        endpoints = {
            "usage": "/agent/log-usage",
            "violation": "/agent/log-violation",
            "end_session": "/agent/end-session",
        }
        sent = 0
        items = self.outbox.pending(limit=limit)

        def mark_batch_failed(batch, error, retry_after=None):
            for queued_item in batch:
                self.outbox.mark_failed(
                    queued_item["event_id"], error, retry_after,
                )

        index = 0
        while index < len(items):
            item = items[index]
            if item["kind"] == "usage":
                batch = [item]
                batch_session_id = item.get("session_id")
                next_index = index + 1
                while (
                    next_index < len(items)
                    and items[next_index]["kind"] == "usage"
                    and items[next_index].get("session_id") == batch_session_id
                ):
                    batch.append(items[next_index])
                    next_index += 1

                try:
                    first_payload = json.loads(batch[0]["payload"])
                    usage_segments = []
                    for queued_item in batch:
                        queued_payload = json.loads(queued_item["payload"])
                        if queued_payload.get("session_id") != first_payload.get("session_id"):
                            raise ValueError("Usage batch contains multiple sessions.")
                        segments = json.loads(queued_payload.get("usage_data", "[]"))
                        if not isinstance(segments, list):
                            raise ValueError("Usage batch payload must contain a list.")
                        usage_segments.extend(segments)

                    delivery_error = None
                    retry_after = None
                    for offset in range(0, len(usage_segments), USAGE_LOG_BATCH_SIZE):
                        batch_payload = dict(first_payload)
                        batch_payload["usage_data"] = json.dumps(
                            usage_segments[offset:offset + USAGE_LOG_BATCH_SIZE],
                            ensure_ascii=False,
                        )
                        response = post_with_retry(
                            f"{API_URL}{endpoints['usage']}",
                            data=_with_device_credentials(batch_payload),
                            headers=_session_auth_headers(self),
                            retries=1,
                            timeout=10,
                        )
                        if response is not None and 200 <= response.status_code < 300:
                            continue

                        status = response.status_code if response is not None else "offline"
                        detail = response_detail(response)
                        delivery_error = f"{status}: {detail}".strip()
                        retry_after = 60 if response is not None else None
                        break

                    if delivery_error is None:
                        for queued_item in batch:
                            self.outbox.mark_sent(queued_item["event_id"])
                        sent += len(batch)
                    else:
                        mark_batch_failed(batch, delivery_error, retry_after)
                except Exception as e:
                    mark_batch_failed(batch, str(e))

                index = next_index
                continue

            endpoint = endpoints.get(item["kind"])
            if not endpoint:
                self.outbox.mark_failed(item["event_id"], "Unknown outbox request type.", 300)
                index += 1
                continue

            try:
                payload = json.loads(item["payload"])
                payload = _with_device_credentials(payload)
                response = post_with_retry(
                    f"{API_URL}{endpoint}",
                    data=payload,
                    headers=_session_auth_headers(self),
                    retries=1,
                    timeout=10,
                )
                if response is not None and 200 <= response.status_code < 300:
                    self.outbox.mark_sent(item["event_id"])
                    sent += 1
                    index += 1
                    continue

                status = response.status_code if response is not None else "offline"
                detail = response_detail(response)
                self.outbox.mark_failed(
                    item["event_id"],
                    f"{status}: {detail}".strip(),
                    60 if response is not None else None,
                )
            except Exception as e:
                self.outbox.mark_failed(item["event_id"], str(e))
            index += 1

        if sent:
            print(f"ส่งข้อมูลจาก local outbox สำเร็จ {sent} รายการ")
        try:
            state_lock = getattr(self, "_outbox_state_lock", None)
            if state_lock is None:
                self._outbox_has_pending = self.outbox.pending_count() > 0
            else:
                with state_lock:
                    self._outbox_has_pending = self.outbox.pending_count() > 0
        except Exception:
            self._outbox_has_pending = True
        return sent

    def set_ui_references(self, overlay):
        self.overlay = overlay

    @staticmethod
    def _has_process_rules(rules):
        return any(
            rule.get("enabled") is not False
            and rule.get("match_type") in {"process_name", "process_name_or_title", "exe_path"}
            for rule in rules
        )

    def _reset_process_scan_state(self, *, clear_pending_events=False):
        self._process_scan_generation = getattr(self, "_process_scan_generation", 0) + 1
        self.seen_process_ids = set()
        self.seen_visible_process_ids = set()
        self.seen_visible_window_handles_by_pid = {}
        self.pending_window_reopen_process_ids = set()
        if clear_pending_events:
            self._process_scan_pending_shown = {}

    def _sync_process_monitor(self):
        should_monitor = bool(
            getattr(self, "current_session_id", None)
            and self._has_process_rules(getattr(self, "policy_rules", []))
        )
        monitor = getattr(self, "window_visibility_monitor", None)
        if should_monitor and monitor is None:
            self._start_window_visibility_monitor()
        elif not should_monitor and monitor is not None:
            self._stop_window_visibility_monitor()

    def _sync_browser_monitor(self):
        rules = getattr(self, "policy_rules", [])
        grace_context = getattr(self, "violation_grace_context", None)
        needs_monitor = bool(
            getattr(self, "current_session_id", None)
            and (
                any(
                    rule.get("match_type") == "website_domain"
                    for rule in rules
                )
                or (
                    grace_context
                    and grace_context.get("detection_source")
                    == "browser_domain"
                )
            )
        )
        monitor = getattr(self, "browser_url_monitor", None)
        if needs_monitor and monitor is None:
            self.browser_url_monitor = BrowserURLMonitor()
        elif not needs_monitor and monitor is not None:
            self.stop_browser_monitor()

    def _set_policy(self, raw_rules, version, source):
        if not isinstance(raw_rules, list):
            return False
        rules = normalize_rules(raw_rules)
        if raw_rules and not rules:
            return False

        changed = rules != self.policy_rules or version != self.policy_version
        self.policy_rules = rules
        self.policy_version = version or "unknown"
        self.policy_source = source
        if changed:
            # Re-check already-running processes when an administrator changes
            # the policy during an active session.
            SmartLabAgent._reset_process_scan_state(self)
        return True

    def _load_cached_policy(self):
        if self.outbox is None:
            return False

        try:
            cached = self.outbox.load_policy_cache("blacklist")
        except Exception as e:
            print(f"อ่าน Blacklist cache ไม่ได้: {e}")
            return False

        if not cached:
            return False

        if self._set_policy(cached.get("data"), cached.get("version"), "cache"):
            self.policy_token = cached.get("policy_token")
            print(f"ใช้ Blacklist จาก cache เวอร์ชัน {self.policy_version}")
            return True
        return False

    def _use_fallback_policy(self):
        self._set_policy(DEFAULT_FALLBACK_RULES, "fallback", "fallback")
        print("ใช้ Blacklist fallback ในตัว Agent")

    def _request_policy(self):
        response = requests.get(f"{API_URL}/agent/policy", timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")

        payload = response.json()
        raw_rules = payload.get("data") if isinstance(payload, dict) else None
        version = payload.get("version") if isinstance(payload, dict) else None
        if not isinstance(raw_rules, list):
            raise ValueError("Backend policy data must be a list")
        rules = normalize_rules(raw_rules)
        if raw_rules and not rules:
            raise ValueError("Backend returned an empty or invalid policy")

        policy_token = payload.get("policy_token")
        if policy_token is not None and not isinstance(policy_token, str):
            raise ValueError("Backend policy token must be a string")
        if self.outbox is not None:
            self.outbox.save_policy_cache(
                "blacklist",
                {"version": version or "unknown", "data": rules, "policy_token": policy_token},
                version=version,
            )
        result = {"rules": rules, "version": version}
        if policy_token:
            result["policy_token"] = policy_token
        return result

    def fetch_policy(self):
        """Fetch policy in the background; apply it on the Qt thread."""
        return self.background_tasks.submit(
            "policy",
            self._request_policy,
            self._handle_policy_result,
        )

    def _handle_policy_result(self, result, error):
        if error is not None:
            print(f"ดึง Blacklist ไม่ได้: {error}")
            if self.policy_source is not None:
                print(f"ใช้ Blacklist เดิมจาก {self.policy_source}")
            else:
                self._use_fallback_policy()
            SmartLabAgent._sync_process_monitor(self)
            SmartLabAgent._sync_browser_monitor(self)
            return

        if not isinstance(result, dict) or not self._set_policy(
            result.get("rules"),
            result.get("version"),
            "backend",
        ):
            print("ดึง Blacklist ไม่ได้: Backend returned an empty or invalid policy")
            if self.policy_source is None:
                self._use_fallback_policy()
            SmartLabAgent._sync_process_monitor(self)
            SmartLabAgent._sync_browser_monitor(self)
            return

        self.policy_token = result.get("policy_token")
        SmartLabAgent._sync_process_monitor(self)
        SmartLabAgent._sync_browser_monitor(self)
        print(
            f"ดึง Blacklist สำเร็จ {len(self.policy_rules)} รายการ "
            f"(เวอร์ชัน {self.policy_version})"
        )

    def refresh_policy(self):
        self.fetch_policy()

    def start_monitoring(self, session_id, info_bar):
        self.current_session_id = session_id
        self.info_bar = info_bar
        self.usage_segments = []
        self.current_activity_name = None
        self.current_activity_started_at = None
        self.policy_rules = []
        self.policy_version = None
        self.policy_source = None
        self.policy_token = None
        SmartLabAgent._reset_process_scan_state(self, clear_pending_events=True)
        getattr(self, "_usage_name_cache", {}).clear()
        self.violation_reported = False
        self.violation_state.reset()
        self.violation_grace_context = None
        self.violation_dialog_active = False
        self.session_cleanup = None
        if SESSION_CLEANUP_ENABLED:
            try:
                self.session_cleanup = SessionCleanupManager(
                    protected_pid=os.getpid(),
                )
                print("เปิดใช้งาน Session Cleanup สำหรับ Session นี้")
            except Exception as e:
                # Cleanup must never prevent a user from starting a Session.
                self.session_cleanup = None
                print(f"เตรียม Session Cleanup ไม่สำเร็จ: {e}")
        self._load_cached_policy()
        if self.policy_source is None:
            # Keep local protection active while the first server request runs.
            self._use_fallback_policy()
        SmartLabAgent._sync_process_monitor(self)
        SmartLabAgent._sync_browser_monitor(self)
        self.refresh_policy()
        self.monitor_timer.start(5000)
        self.heartbeat_timer.start(30000)
        self.policy_timer.start(POLICY_REFRESH_SECONDS * 1000)

    def send_heartbeat(self):
        session_id = self.current_session_id
        if not session_id:
            return

        self.background_tasks.submit(
            "heartbeat",
            lambda: self._send_heartbeat_request(session_id),
            lambda result, error: self._handle_heartbeat_result(
                session_id,
                result,
                error,
            ),
        )

    def _send_heartbeat_request(self, session_id):
        response = post_with_retry(
            f"{API_URL}/agent/heartbeat",
            data={
                "session_id": session_id,
                "device_mac": DEVICE_MAC,
                "device_id": REGISTERED_DEVICE_ID or None,
                "device_token": DEVICE_TOKEN or None,
            },
            headers=_session_auth_headers(self),
            retries=1,
            timeout=10,
        )
        if response is not None and 200 <= response.status_code < 300:
            # Successful heartbeat is also the reconnect signal for the outbox.
            self.flush_outbox(limit=3)
        return {"status": response.status_code if response is not None else None}

    def _handle_heartbeat_result(self, session_id, result, error):
        if error is not None:
            print(f"ส่ง heartbeat ไม่ได้: {error}")
            return
        if self.current_session_id != session_id:
            return

        status = result.get("status") if isinstance(result, dict) else None
        if status in {403, 409}:
            print("Session ไม่ active แล้ว กำลังกลับไปหน้า Login")
            self.heartbeat_timer.stop()
            if self.info_bar:
                self.info_bar.trigger_logout()
        elif status is None:
            print("ส่ง heartbeat ไม่ได้: Server ไม่ตอบกลับ")

    def _close_current_activity(self, ended_at=None):
        if not self.current_activity_name or not self.current_activity_started_at:
            return

        ended_at = ended_at or _utc_now()
        duration = max(
            0,
            int((ended_at - self.current_activity_started_at).total_seconds()),
        )
        if duration > 0:
            segment = {
                "event_id": uuid.uuid4().hex,
                "name": self.current_activity_name,
                "started_at": self.current_activity_started_at.isoformat(timespec="seconds"),
                "ended_at": ended_at.isoformat(timespec="seconds"),
                "duration": duration,
            }
            queued = self._queue_outbox(
                kind="usage",
                payload={
                    "session_id": self.current_session_id,
                    "usage_data": json.dumps([segment], ensure_ascii=False),
                },
                session_id=self.current_session_id,
                event_id=segment["event_id"],
            )
            if not queued:
                # Keep only segments that could not be durably queued. Successfully
                # queued events are already recoverable from SQLite after a crash.
                self.usage_segments.append(segment)
            print(f"บันทึก: [{self.current_activity_name}] {duration} วินาที")

        self.current_activity_name = None
        self.current_activity_started_at = None

    def _track_active_activity(self, app_name, observed_at):
        if not app_name or app_name in IGNORE_SYSTEM_APPS:
            self._close_current_activity(observed_at)
            return

        if app_name == self.current_activity_name:
            return

        self._close_current_activity(observed_at)
        self.current_activity_name = app_name
        self.current_activity_started_at = observed_at

    def _usage_name_for_active_window(self, window):
        process_id = _window_process_id(window)
        if not process_id:
            return _usage_name_for_window(window)
        if _is_agent_window(window, process_id):
            return None
        handle = getattr(window, "_hWnd", None)
        if not handle:
            return _usage_name_for_window(window, process_id=process_id)

        key = (process_id, int(handle))
        cache = getattr(self, "_usage_name_cache", None)
        if cache is None:
            cache = {}
            self._usage_name_cache = cache
        if key in cache:
            return cache[key]

        name = _usage_name_for_window(window, process_id=process_id)
        if len(cache) >= 128:
            cache.clear()
        if name is not None:
            cache[key] = name
        return name

    def _checkpoint_current_activity(self, observed_at):
        """Persist a running app periodically without overlapping its segments."""
        if not self.current_activity_name or not self.current_activity_started_at:
            return
        if (observed_at - self.current_activity_started_at).total_seconds() < USAGE_CHECKPOINT_SECONDS:
            return
        app_name = self.current_activity_name
        self._close_current_activity(observed_at)
        self.current_activity_name = app_name
        self.current_activity_started_at = observed_at

    def _finalize_violation(self, context, show_dialog=True):
        """Record the final violation and close the current lab session."""
        self.report_violation(
            context["program_name"],
            context["reason"],
            process_name=context.get("process_name"),
            exe_path=context.get("exe_path"),
            window_title=context.get("window_title"),
            detection_source=context.get("detection_source"),
            detected_at=context.get("detected_at"),
            policy_version=context.get("policy_version"),
            policy_token=context.get("policy_token"),
            executable_identity=context.get("executable_identity"),
            browser_domain=context.get("browser_domain"),
        )
        if self.info_bar:
            self.info_bar.trigger_logout(
                reason=context["reason"],
                show_dialog=show_dialog,
            )

    def _handle_violation_detection(self, context):
        """Give two five-minute chances before enforcing the third detection."""
        if (
            not self.current_session_id
            or self.violation_reported
            or self.violation_dialog_active
        ):
            return

        context = dict(context)
        context.setdefault("detected_at", _utc_now().isoformat(timespec="seconds"))
        context.setdefault("policy_version", self.policy_version)
        context.setdefault("policy_token", self.policy_token)
        now = datetime.now()
        if self.violation_state.clear_expired_grace(now):
            # The original process may already be in seen_process_ids. Clear it
            # so the five-minute recheck inspects the process again.
            self.violation_grace_context = None
            self._reset_process_scan_state()

        if self.violation_state.is_grace_active(now):
            return

        attempt = self.violation_state.register_detection(now)
        if attempt is None:
            return

        if attempt.must_terminate:
            final_context = dict(context)
            final_context["reason"] = (
                f"{context['reason']} (ตรวจพบซ้ำครั้งที่ {attempt.number})"
            )
            self.monitor_timer.stop()
            self.violation_dialog_active = True
            try:
                self._finalize_violation(final_context, show_dialog=True)
            finally:
                self.violation_dialog_active = False
            return

        self.violation_dialog_active = True
        self.monitor_timer.stop()
        chance_requested = False
        try:
            dialog = ViolationDialog(
                context["reason"],
                attempt=attempt.number,
                max_attempts=self.violation_state.max_attempts,
                allow_grace=True,
                warning_seconds=DEFAULT_WARNING_SECONDS,
                grace_seconds=self.violation_state.grace_seconds,
            )
            chance_requested = dialog.exec() == QDialog.DialogCode.Accepted
        except Exception as exc:
            # If the warning cannot be shown, fail closed instead of leaving
            # the session running with its monitor stopped.
            print(f"แสดงหน้าต่างแจ้งเตือนไม่ได้: {exc}")
        finally:
            self.violation_dialog_active = False

        if chance_requested:
            grace_until = self.violation_state.grant_grace(datetime.now())
            self.violation_grace_context = context
            print(
                f"ให้โอกาสครั้งที่ {attempt.number} ถึง "
                f"{grace_until.isoformat(timespec='seconds')}"
            )
            if self.current_session_id and not self.violation_reported:
                self.monitor_timer.start(5000)
            return

        # The warning itself takes focus. Recheck EXE identity or the original
        # browser window rather than treating the warning as the active app.
        try:
            still_present = self._violation_is_still_present(context)
        except Exception as exc:
            print(f"ตรวจโปรแกรมซ้ำไม่ได้: {exc}")
            still_present = True
        if not still_present:
            if self.current_session_id and not self.violation_reported:
                self.monitor_timer.start(5000)
            return

        timeout_context = dict(context)
        timeout_context["reason"] = (
            f"{context['reason']} (ไม่ขอโอกาสภายในเวลาที่กำหนด)"
        )
        session_id = self.current_session_id
        runner = getattr(self, "background_tasks", None)
        if runner is None:
            try:
                still_present = self._violation_is_still_present(context)
            except Exception as exc:
                print(f"ตรวจโปรแกรมซ้ำไม่ได้: {exc}")
                still_present = True
            self._complete_violation_recheck(
                session_id, context, timeout_context, still_present,
            )
            return

        submitted = runner.submit(
            f"violation-recheck-{session_id}",
            lambda: self._violation_is_still_present(context),
            lambda result, error: self._handle_violation_recheck_result(
                session_id, context, timeout_context, result, error,
            ),
        )
        if not submitted:
            # A failed recheck submission must preserve the prior fail-closed
            # behavior rather than leave the monitor stopped.
            self._finalize_violation(timeout_context, show_dialog=False)

    def _handle_violation_recheck_result(
        self, session_id, context, timeout_context, result, error,
    ):
        if error is not None:
            print(f"ตรวจโปรแกรมซ้ำไม่ได้: {error}")
            still_present = True
        else:
            still_present = bool(result)
        self._complete_violation_recheck(
            session_id, context, timeout_context, still_present,
        )

    def _complete_violation_recheck(
        self, session_id, context, timeout_context, still_present,
    ):
        if self.current_session_id != session_id:
            return
        if not still_present:
            if self.current_session_id and not self.violation_reported:
                self.monitor_timer.start(5000)
            return
        self._finalize_violation(timeout_context, show_dialog=False)

    def _violation_is_still_present(self, context, policy_rules=None):
        rules = (
            [context["matched_rule"]]
            if context.get("matched_rule")
            else (self.policy_rules if policy_rules is None else policy_rules)
        )
        if context.get("detection_source") == "browser_domain":
            monitor = getattr(self, "browser_url_monitor", None)
            observation = monitor.recheck(context) if monitor else None
            return bool(observation and find_website_match(rules, observation["domain"]))
        if context.get("detection_source") == "window_title":
            return False
        target_process_id = context.get("process_id")
        target_had_visible_window = context.get("process_window_visible")
        visible_process_ids = (
            _visible_window_process_ids() if target_had_visible_window else None
        )
        if (
            target_had_visible_window
            and target_process_id not in visible_process_ids
        ):
            return False
        if target_process_id is not None:
            try:
                process = psutil.Process(target_process_id)
                name = process.name()
                path = process.exe()
                identity = read_executable_identity(path)
                return bool(find_process_match(rules, name, path, identity))
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                return False
        for process in psutil.process_iter(["pid", "name"]):
            try:
                process_id = process.info.get("pid")
                if process_id == os.getpid():
                    continue
                if target_process_id is not None and process_id != target_process_id:
                    continue
                name = process.info.get("name") or ""
                path = process.exe()
                identity = read_executable_identity(path)
                if find_process_match(rules, name, path, identity):
                    return True
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            except psutil.AccessDenied:
                # A matching observed name alone cannot establish EXE identity.
                continue
        return False

    def report_violation(
        self,
        program_name,
        reason,
        *,
        process_name=None,
        exe_path=None,
        window_title=None,
        detection_source=None,
        detected_at=None,
        policy_version=None,
        policy_token=None,
        executable_identity=None,
        browser_domain=None,
    ):
        if self.violation_reported or not self.current_session_id:
            return

        event_id = uuid.uuid4().hex
        payload = {
            "session_id": self.current_session_id,
            "program_name": program_name,
            "reason": reason,
            "action_taken": "logout",
            "event_id": event_id,
            "process_name": process_name,
            "exe_path": exe_path,
            "window_title": window_title,
            "detection_source": detection_source,
            "detected_at": detected_at or _utc_now().isoformat(timespec="seconds"),
            "policy_version": policy_version,
            "policy_token": policy_token,
            "executable_identity": json.dumps(executable_identity or {}, ensure_ascii=False),
            "browser_domain": browser_domain,
        }

        if self._queue_outbox(
            kind="violation",
            payload=payload,
            session_id=self.current_session_id,
            event_id=event_id,
        ):
            # Session shutdown will flush this durable event with the end log.
            self.violation_reported = True
            return

        # Keep the degraded fallback ordered with session/end logs, but never
        # perform the request on the UI thread.
        self._pending_fallback_violations.append(payload)

    def _start_window_visibility_monitor(self):
        self._stop_window_visibility_monitor()
        try:
            self.window_visibility_monitor = WindowVisibilityMonitor(
                ignored_process_id=os.getpid(),
            )
        except Exception as exc:
            self.window_visibility_monitor = None
            print(f"ติดตามการเปิดหน้าต่างแบบ event ไม่สำเร็จ ใช้การตรวจตามรอบแทน: {exc}")

    def _stop_window_visibility_monitor(self):
        monitor = getattr(self, "window_visibility_monitor", None)
        self.window_visibility_monitor = None
        if monitor is not None:
            try:
                monitor.close()
            except Exception as exc:
                print(f"หยุดการติดตามหน้าต่างไม่สำเร็จ: {exc}")

    def _consume_shown_process_ids(self):
        monitor = getattr(self, "window_visibility_monitor", None)
        if monitor is None:
            return set()
        try:
            return monitor.consume_shown_process_ids()
        except Exception as exc:
            print(f"อ่าน event การเปิดหน้าต่างไม่สำเร็จ: {exc}")
            self._stop_window_visibility_monitor()
            return set()

    def _process_scan_job(self, snapshot):
        grace_present = None
        should_scan = not snapshot["grace_active"]
        context = snapshot["grace_context"]
        if snapshot["grace_active"] and context:
            if context.get("process_id") in snapshot["shown_process_ids"]:
                grace_present = False
            else:
                try:
                    grace_present = self._violation_is_still_present(
                        snapshot["grace_context_copy"],
                        policy_rules=snapshot["policy_rules"],
                    )
                except Exception:
                    # Preserve the existing fail-closed behavior during a grace
                    # recheck if process/browser state cannot be read.
                    grace_present = True
            should_scan = not grace_present

        scan_result = None
        if should_scan and snapshot["has_process_rules"]:
            scanner = SimpleNamespace(
                policy_rules=snapshot["policy_rules"],
                seen_process_ids=snapshot["seen_process_ids"],
                seen_visible_process_ids=snapshot["seen_visible_process_ids"],
                seen_visible_window_handles_by_pid=snapshot[
                    "seen_visible_window_handles_by_pid"
                ],
                pending_window_reopen_process_ids=snapshot[
                    "pending_window_reopen_process_ids"
                ],
                window_visibility_monitor=None,
            )
            match = SmartLabAgent._find_new_process_match(
                scanner, snapshot["shown_process_ids"],
            )
            scan_result = {
                "match": match,
                "seen_process_ids": scanner.seen_process_ids,
                "seen_visible_process_ids": scanner.seen_visible_process_ids,
                "seen_visible_window_handles_by_pid": (
                    scanner.seen_visible_window_handles_by_pid
                ),
                "pending_window_reopen_process_ids": (
                    scanner.pending_window_reopen_process_ids
                ),
            }

        return {"grace_present": grace_present, "scan": scan_result}

    def _queue_process_scan(self, shown_process_ids, grace_active):
        pending_shown = getattr(self, "_process_scan_pending_shown", None)
        if pending_shown is None:
            pending_shown = {}
            self._process_scan_pending_shown = pending_shown
        for process_id in shown_process_ids:
            pending_shown[process_id] = pending_shown.get(process_id, 0) + 1

        policy_rules = getattr(self, "policy_rules", [])
        has_process_rules = self._has_process_rules(policy_rules)
        grace_context = getattr(self, "violation_grace_context", None) if grace_active else None
        if grace_active and not grace_context:
            pending_shown.clear()
            return None
        if not has_process_rules and not grace_context:
            pending_shown.clear()
            return None
        if getattr(self, "_process_scan_in_flight", False):
            return "pending"

        shown_snapshot = set(pending_shown)
        shown_counts = dict(pending_shown)
        grace_context_copy = None
        if grace_context:
            grace_context_copy = dict(grace_context)
            if isinstance(grace_context.get("matched_rule"), dict):
                grace_context_copy["matched_rule"] = dict(
                    grace_context["matched_rule"]
                )

        snapshot = {
            "session_id": self.current_session_id,
            "generation": getattr(self, "_process_scan_generation", 0),
            "policy_rules": [dict(rule) for rule in policy_rules],
            "has_process_rules": has_process_rules,
            "grace_active": grace_active,
            "grace_context": grace_context,
            "grace_context_copy": grace_context_copy,
            "shown_process_ids": shown_snapshot,
            "shown_counts": shown_counts,
            "seen_process_ids": set(getattr(self, "seen_process_ids", set())),
            "seen_visible_process_ids": set(
                getattr(self, "seen_visible_process_ids", set())
            ),
            "seen_visible_window_handles_by_pid": {
                process_id: set(handles)
                for process_id, handles in getattr(
                    self, "seen_visible_window_handles_by_pid", {}
                ).items()
            },
            "pending_window_reopen_process_ids": set(
                getattr(self, "pending_window_reopen_process_ids", set())
            ),
        }

        def operation():
            return self._process_scan_job(snapshot)

        def completed(result, error):
            self._handle_process_scan_result(snapshot, result, error)

        runner = getattr(self, "background_tasks", None)
        if runner is None:
            # Keep lightweight objects usable in offline tools and unit tests;
            # the real Agent always owns a BackgroundTaskRunner.
            try:
                result = self._process_scan_job_inline(snapshot)
            except Exception as error:
                completed(None, error)
                return None
            else:
                completed(result, None)
                if result and result.get("scan") and result["scan"].get("match"):
                    return "matched"
                return None

        self._process_scan_in_flight = True
        submitted = runner.submit("process-scan", operation, completed)
        if not submitted:
            self._process_scan_in_flight = False
            return None
        return "pending"

    def _process_scan_job_inline(self, snapshot):
        grace_present = None
        should_scan = not snapshot["grace_active"]
        context = snapshot["grace_context"]
        if snapshot["grace_active"] and context:
            if context.get("process_id") in snapshot["shown_process_ids"]:
                grace_present = False
            else:
                try:
                    grace_present = self._violation_is_still_present(
                        snapshot["grace_context_copy"],
                        policy_rules=snapshot["policy_rules"],
                    )
                except Exception:
                    grace_present = True
            should_scan = not grace_present

        scan_result = None
        if should_scan and snapshot["has_process_rules"]:
            match = self._find_new_process_match(
                snapshot["shown_process_ids"], prune_window_monitor=False,
            )
            scan_result = {
                "match": match,
                "seen_process_ids": getattr(self, "seen_process_ids", set()),
                "seen_visible_process_ids": getattr(
                    self, "seen_visible_process_ids", set()
                ),
                "seen_visible_window_handles_by_pid": getattr(
                    self, "seen_visible_window_handles_by_pid", {}
                ),
                "pending_window_reopen_process_ids": getattr(
                    self, "pending_window_reopen_process_ids", set()
                ),
            }
        return {"grace_present": grace_present, "scan": scan_result}

    def _handle_process_scan_result(self, snapshot, result, error):
        self._process_scan_in_flight = False
        if error is not None:
            print(f"ตรวจรายการโปรแกรมไม่สำเร็จ: {error}")
            return
        if (
            snapshot["session_id"] != self.current_session_id
            or snapshot["generation"] != getattr(self, "_process_scan_generation", 0)
        ):
            return
        if not isinstance(result, dict):
            return

        if snapshot["grace_active"] and snapshot["grace_context"]:
            if self.violation_grace_context is not snapshot["grace_context"]:
                return
            if result["grace_present"]:
                return
            self.violation_state.clear_grace()
            self.violation_grace_context = None

        scan = result.get("scan")
        if not scan:
            return

        self.seen_process_ids = scan["seen_process_ids"]
        self.seen_visible_process_ids = scan["seen_visible_process_ids"]
        self.seen_visible_window_handles_by_pid = scan[
            "seen_visible_window_handles_by_pid"
        ]
        self.pending_window_reopen_process_ids = scan[
            "pending_window_reopen_process_ids"
        ]
        pending_shown = getattr(self, "_process_scan_pending_shown", {})
        for process_id, consumed_count in snapshot["shown_counts"].items():
            current_count = pending_shown.get(process_id, 0)
            if current_count <= consumed_count:
                pending_shown.pop(process_id, None)
            else:
                pending_shown[process_id] = current_count - consumed_count

        monitor = getattr(self, "window_visibility_monitor", None)
        if monitor is not None:
            try:
                monitor.prune(self.seen_process_ids)
            except Exception as exc:
                print(f"ล้างสถานะ event หน้าต่างเก่าไม่สำเร็จ: {exc}")

        match = scan.get("match")
        if match is None or not self.current_session_id or self.violation_dialog_active:
            return
        if self.violation_state.is_grace_active(datetime.now()):
            return

        (
            process_name,
            exe_path,
            matched_rule,
            detection_source,
            identity,
            process_id,
            process_window_visible,
        ) = match
        rule_name = matched_rule.get("app_name") or matched_rule.get("match_value")
        self._handle_violation_detection(
            {
                "program_name": (
                    identity.get("original_filename") or identity.get("internal_name")
                    or identity.get("product_name") or process_name
                ),
                "reason": f"ไม่อนุญาตให้เปิดแอป: {rule_name}",
                "process_name": process_name,
                "process_id": process_id,
                "process_window_visible": process_window_visible,
                "exe_path": exe_path,
                "window_title": None,
                "detection_source": detection_source,
                "matched_rule": matched_rule,
                "executable_identity": identity,
            }
        )

    def _find_new_process_match(self, shown_process_ids=None, *, prune_window_monitor=True):
        """Inspect newly started processes and re-opened visible apps once."""
        shown_process_ids = set(shown_process_ids or ())
        current_process_ids = set()
        current_visible_window_handles_by_pid = _visible_window_handles_by_pid()
        current_visible_process_ids = set(current_visible_window_handles_by_pid)
        previous_visible_process_ids = getattr(self, "seen_visible_process_ids", set())
        previous_visible_window_handles_by_pid = getattr(
            self, "seen_visible_window_handles_by_pid", {}
        )
        pending_reopens = set(getattr(self, "pending_window_reopen_process_ids", set()))
        added_window_process_ids = set()
        for process_id in (
            set(previous_visible_window_handles_by_pid)
            | set(current_visible_window_handles_by_pid)
        ):
            previous_handles = previous_visible_window_handles_by_pid.get(process_id, set())
            current_handles = current_visible_window_handles_by_pid.get(process_id, set())
            if previous_handles - current_handles:
                pending_reopens.add(process_id)
            if current_handles - previous_handles:
                added_window_process_ids.add(process_id)

        reopened_window_process_ids = pending_reopens & added_window_process_ids
        pending_reopens.difference_update(added_window_process_ids)
        self.seen_visible_window_handles_by_pid = current_visible_window_handles_by_pid
        match = None

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                process_id = proc.info.get("pid")
                if process_id is None:
                    continue
                current_process_ids.add(process_id)
                if process_id == os.getpid():
                    continue
                newly_started = process_id not in self.seen_process_ids
                newly_visible = (
                    process_id in current_visible_process_ids
                    and process_id not in previous_visible_process_ids
                )
                reopened_window = process_id in reopened_window_process_ids
                shown_again = process_id in shown_process_ids
                if not newly_started and not newly_visible and not reopened_window and not shown_again:
                    continue

                process_name = (proc.info.get("name") or "").strip()
                exe_path = proc.exe()
                identity = read_executable_identity(exe_path)
                matched_rule = find_process_match(self.policy_rules, process_name, exe_path, identity)

                if matched_rule is not None and match is None:
                    detection_source = (
                        "exe_path"
                        if matched_rule["match_type"] == "exe_path"
                        else "executable_identity"
                    )
                    match = (
                        process_name,
                        exe_path,
                        matched_rule,
                        detection_source,
                        identity,
                        process_id,
                        process_id in current_visible_process_ids,
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        self.seen_process_ids = current_process_ids
        self.seen_visible_process_ids = current_visible_process_ids
        pending_reopens.intersection_update(current_process_ids)
        self.pending_window_reopen_process_ids = pending_reopens
        monitor = getattr(self, "window_visibility_monitor", None)
        if monitor is not None and prune_window_monitor:
            try:
                monitor.prune(current_process_ids)
            except Exception as exc:
                print(f"ล้างสถานะ event หน้าต่างเก่าไม่สำเร็จ: {exc}")
        return match

    def track_usage(self):
        try:
            if not self.current_session_id or self.violation_dialog_active:
                return

            shown_process_ids = self._consume_shown_process_ids()
            self._checkpoint_current_activity(_utc_now())
            now = datetime.now()
            if self.violation_state.clear_expired_grace(now):
                # A running forbidden process was intentionally skipped during
                # the grace period, so it must be checked again now.
                self.violation_grace_context = None
                self._reset_process_scan_state()

            grace_active = self.violation_state.is_grace_active(now)
            process_scan_status = self._queue_process_scan(
                shown_process_ids, grace_active,
            )
            if process_scan_status == "matched":
                return

            if not grace_active and process_scan_status != "pending" and any(
                rule.get("match_type") == "website_domain" for rule in self.policy_rules
            ):
                if getattr(self, "browser_url_monitor", None) is None:
                    self.browser_url_monitor = BrowserURLMonitor()
                observation = self.browser_url_monitor.poll()
                matched_rule = find_website_match(self.policy_rules, observation["domain"]) if observation else None
                if matched_rule:
                    self._handle_violation_detection({
                        "program_name": observation["domain"],
                        "reason": f"ไม่อนุญาตให้เข้าเว็บไซต์: {observation['domain']}",
                        "browser_domain": observation["domain"],
                        "browser_hwnd": observation["hwnd"], "browser_pid": observation["pid"],
                        "process_name": observation["process_name"], "exe_path": observation["exe_path"],
                        "executable_identity": observation["executable_identity"],
                        "detection_source": "browser_domain", "matched_rule": matched_rule,
                    })
                    return

            # Usage follows the foreground window's executable, not its title.
            active_win = gw.getActiveWindow()
            app_name = self._usage_name_for_active_window(active_win) if active_win else None
            self._track_active_activity(app_name, _utc_now())
            self._last_track_usage_error = None

        except Exception as exc:
            error_type = type(exc).__name__
            now = time.monotonic()
            last_error = getattr(self, "_last_track_usage_error", None)
            if last_error is None or last_error[0] != error_type or now - last_error[1] >= 60:
                _append_monitor_error_log(error_type)
                self._last_track_usage_error = (error_type, now)

    def _cleanup_session(self):
        cleanup = self.session_cleanup
        self.session_cleanup = None
        if cleanup is None:
            return

        try:
            report = cleanup.cleanup()
            print(
                "Session Cleanup: "
                f"ปิดโปรแกรม {report.closed_processes} รายการ, "
                f"บังคับปิด {report.force_closed_processes} รายการ, "
                f"ล้างข้อมูล Browser {report.removed_browser_items} รายการ, "
                f"ลบไฟล์ใหม่ใน Downloads {report.removed_downloads} รายการ"
            )
            if report.errors:
                print(f"Session Cleanup มีบางส่วนทำไม่สำเร็จ: {', '.join(report.errors)}")
        except Exception as e:
            # Session delivery has already been queued before cleanup starts;
            # an unexpected cleanup error must not interrupt logout.
            print(f"Session Cleanup ล้มเหลว: {e}")

    def _send_fallback_session_logs(
        self,
        session_id,
        summary,
        end_reason,
        violations,
    ):
        self._send_fallback_violation_logs(violations)

        if summary:
            for offset in range(0, len(summary), USAGE_LOG_BATCH_SIZE):
                batch = summary[offset:offset + USAGE_LOG_BATCH_SIZE]
                try:
                    response = post_with_retry(
                        f"{API_URL}/agent/log-usage",
                        data=_with_device_credentials({
                            "session_id": session_id,
                            "usage_data": json.dumps(batch, ensure_ascii=False),
                        }),
                        headers=_session_auth_headers(self),
                    )
                    print(f"Server Response: {response.status_code if response is not None else 'Timeout'}")
                except Exception as error:
                    print(f"ส่งข้อมูลไม่ได้: {error}")
        else:
            print("ไม่มีสถิติการใช้งานที่บันทึกได้")

        try:
            response = post_with_retry(
                f"{API_URL}/agent/end-session",
                data=_with_device_credentials({
                    "session_id": session_id,
                    "end_reason": end_reason,
                }),
                headers=_session_auth_headers(self),
            )
            print(f"End session response: {response.status_code if response is not None else 'Timeout'}")
        except Exception as error:
            print(f"ปิด Session ไม่ได้: {error}")

    def _send_fallback_violation_logs(self, violations):
        for payload in violations:
            try:
                response = post_with_retry(
                    f"{API_URL}/agent/log-violation",
                    data=_with_device_credentials(payload),
                    headers=_session_auth_headers(self),
                )
                print(f"Violation response: {response.status_code if response is not None else 'Timeout'}")
            except Exception as error:
                print(f"บันทึก violation ไม่ได้: {error}")

    def stop_and_send_logs(self, session_id, end_reason="logout"):
        self.stop_browser_monitor()
        self._stop_window_visibility_monitor()
        self.monitor_timer.stop()
        self.heartbeat_timer.stop()
        self.policy_timer.stop()
        self._close_current_activity(_utc_now())
        summary = list(self.usage_segments)

        print("\n--- บันทึกข้อมูลลง local outbox ---")
        print(f"Data: {summary}")

        logoff_immediately = not DEBUG_MODE and self.outbox is not None
        if self.outbox is not None:
            violations = list(self._pending_fallback_violations)
            self._pending_fallback_violations.clear()
            fallback_violations = []
            for payload in violations:
                if not self._queue_outbox(
                    kind="violation",
                    payload=payload,
                    session_id=session_id,
                    event_id=payload.get("event_id"),
                ):
                    fallback_violations.append(payload)
            logoff_after_fallback = bool(fallback_violations) and not DEBUG_MODE
            if logoff_after_fallback:
                logoff_immediately = False

            # Retry only segments that could not be saved to the outbox when
            # their activity ended; already queued items may have been delivered.
            for segment in summary:
                self._queue_outbox(
                    kind="usage",
                    payload={
                        "session_id": session_id,
                        "usage_data": json.dumps([segment], ensure_ascii=False),
                    },
                    session_id=session_id,
                    event_id=segment.get("event_id"),
                )

            self._queue_outbox(
                kind="end_session",
                payload={
                    "session_id": session_id,
                    "end_reason": end_reason,
                },
                session_id=session_id,
                event_id=f"end-session-{session_id}",
            )

            def deliver_outbox():
                if fallback_violations:
                    self._send_fallback_violation_logs(fallback_violations)
                self.flush_outbox(limit=10)
                return self.outbox.has_pending_for_session(session_id)

            def handle_outbox_delivery(pending, error):
                if error is not None:
                    print(f"ส่งข้อมูลจาก local outbox ไม่สำเร็จ: {error}")
                elif pending:
                    print("ยังมีข้อมูลรอส่ง จะ retry อัตโนมัติเมื่อ Internet กลับมา")
                if logoff_after_fallback:
                    os.system("shutdown /l /f")

            submitted = self.background_tasks.submit(
                f"outbox-session-{session_id}",
                deliver_outbox,
                handle_outbox_delivery,
            )
            if logoff_after_fallback and not submitted:
                os.system("shutdown /l /f")
        else:
            violations = list(self._pending_fallback_violations)
            self._pending_fallback_violations.clear()

            def handle_fallback_delivery(_result, error):
                if error is not None:
                    print(f"ส่งบันทึก Session ไม่สำเร็จ: {error}")
                if not DEBUG_MODE:
                    os.system("shutdown /l /f")

            self.background_tasks.submit(
                f"fallback-session-{session_id}",
                lambda: self._send_fallback_session_logs(
                    session_id,
                    summary,
                    end_reason,
                    violations,
                ),
                handle_fallback_delivery,
            )

        self._cleanup_session()
        self.usage_segments = []
        self.current_activity_name = None
        self.current_activity_started_at = None
        self.policy_rules = []
        self.policy_version = None
        self.policy_source = None
        self.policy_token = None
        self._reset_process_scan_state(clear_pending_events=True)
        getattr(self, "_usage_name_cache", {}).clear()
        self.violation_state.reset()
        self.violation_grace_context = None
        self.violation_dialog_active = False
        self.current_session_id = None

        if logoff_immediately:
            os.system("shutdown /l /f")

    def stop_browser_monitor(self):
        monitor = getattr(self, "browser_url_monitor", None)
        if monitor is not None:
            monitor.close()
            self.browser_url_monitor = None


def run_agent() -> int:
    """Start the Agent UI and return its Qt event-loop exit code."""

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    agent_logic  = SmartLabAgent()
    app.aboutToQuit.connect(agent_logic.stop_browser_monitor)
    app.aboutToQuit.connect(agent_logic._stop_window_visibility_monitor)
    login_screen = LoginOverlay(agent_logic)
    login_screen.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_agent())
