import sys
import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import psutil
import json
import sqlite3
import socket
import time
import uuid
import requests
import ctypes
import pygetwindow as gw
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QFrame,
                             QGraphicsDropShadowEffect, QMessageBox, QDialog)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

# ── LOGGING SETUP ─────────────────────────────────────────────────────────────
# ป้องกัน crash: .pyw / windowed .exe จะมี sys.stdout = None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

LOG_DIR = Path(os.getenv("APPDATA", ".")) / "SmartLabAgent" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("SmartLabAgent")
logger.setLevel(logging.DEBUG)

_file_handler = RotatingFileHandler(
    LOG_DIR / "agent.log",
    maxBytes=2 * 1024 * 1024,   # 2 MB per file
    backupCount=5,              # keep 5 rotated files
    encoding="utf-8",
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logger.addHandler(_file_handler)

# console handler เฉพาะตอน dev (stdout ใช้งานได้จริง)
if sys.stdout is not None and hasattr(sys.stdout, "fileno"):
    try:
        sys.stdout.fileno()  # จะ raise ถ้าเป็น devnull redirect
        _console_handler = logging.StreamHandler(sys.stdout)
        _console_handler.setLevel(logging.INFO)
        _console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(_console_handler)
    except (OSError, ValueError):
        pass

logger.info("Smart Lab Agent starting up...")


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


# ── NetworkWorker ─────────────────────────────────────────────────────────────
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


# ── PendingLogStore ────────────────────────────────────────────────────────────
DATA_DIR = Path(os.getenv("APPDATA", ".")) / "SmartLabAgent"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class PendingLogStore:
    """เก็บ usage logs ลง SQLite ก่อนส่ง — ป้องกัน data loss เมื่อ network ล้มเหลว."""

    def __init__(self, db_path: Path = None):
        self._db_path = db_path or (DATA_DIR / "pending_logs.db")
        self._ensure_table()

    def _connect(self):
        return sqlite3.connect(str(self._db_path), timeout=5)

    def _ensure_table(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_logs (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT    NOT NULL,
                    usage_data TEXT    NOT NULL,
                    hostname   TEXT    DEFAULT '',
                    mac_address TEXT   DEFAULT '',
                    created_at TEXT    DEFAULT (datetime('now','localtime'))
                )
            """)
            # Migration: เพิ่ม column ใหม่ถ้า DB เก่ายังไม่มี
            existing = {row[1] for row in conn.execute("PRAGMA table_info(pending_logs)")}
            if "hostname" not in existing:
                conn.execute("ALTER TABLE pending_logs ADD COLUMN hostname TEXT DEFAULT ''")
            if "mac_address" not in existing:
                conn.execute("ALTER TABLE pending_logs ADD COLUMN mac_address TEXT DEFAULT ''")

    def save(self, session_id: str, summary: list,
             hostname: str = "", mac_address: str = "") -> int:
        """บันทึก log ลง local DB ก่อนส่ง — return row id."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO pending_logs (session_id, usage_data, hostname, mac_address) VALUES (?, ?, ?, ?)",
                (session_id, json.dumps(summary, ensure_ascii=False), hostname, mac_address),
            )
            row_id = cur.lastrowid
            logger.info(f"Saved pending log id={row_id} for session={session_id} device={hostname}")
            return row_id

    def delete(self, row_id: int):
        """ลบ log ที่ส่งสำเร็จแล้ว."""
        with self._connect() as conn:
            conn.execute("DELETE FROM pending_logs WHERE id = ?", (row_id,))
            logger.info(f"Deleted pending log id={row_id}")

    def get_all_pending(self) -> list:
        """ดึง logs ที่ยังค้างส่งทั้งหมด — return list of (id, session_id, usage_data_json, hostname, mac_address)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, session_id, usage_data, hostname, mac_address FROM pending_logs ORDER BY id"
            ).fetchall()
            return rows


# ── CONFIG ────────────────────────────────────────────────────────────────────
API_URL    = "https://h0sh1na-smart-lab-backend.hf.space"
LAB_CODE   = "LAB01"
DEBUG_MODE = True   # ← เปลี่ยนเป็น False ก่อน deploy จริง

# ── Device Identity (คำนวณครั้งเดียวตอนเปิด) ─────────────────────────────────
DEVICE_HOSTNAME = socket.gethostname()
DEVICE_MAC = ':'.join(f'{b:02x}' for b in uuid.getnode().to_bytes(6, 'big'))
logger.info(f"Device: {DEVICE_HOSTNAME} (MAC: {DEVICE_MAC})")

IGNORE_SYSTEM_APPS = [
    "Taskbar", "Program Manager", "Settings",
    "Windows Default Lock Screen", "Search",
]


# ── Violation Dialog ──────────────────────────────────────────────────────────
class ViolationDialog(QDialog):
    def __init__(self, reason, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog
        )
        self.setStyleSheet("""
            QDialog { background-color: #fef2f2; border: 3px solid #ef4444; border-radius: 15px; }
            QLabel  { border: none; }
        """)
        self.setFixedSize(550, 250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel("⚠️ ตรวจพบการละเมิดข้อตกลง")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        title.setStyleSheet("color: #dc2626;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        reason_lbl = QLabel(f"สาเหตุ: {reason}")
        reason_lbl.setFont(QFont("Segoe UI", 14))
        reason_lbl.setStyleSheet("color: #7f1d1d; margin-top: 10px;")
        reason_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reason_lbl.setWordWrap(True)

        self.countdown_lbl = QLabel("ระบบจะบังคับปิดเซสชันใน 5 วินาที...")
        self.countdown_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.countdown_lbl.setStyleSheet("color: #ef4444; margin-top: 20px;")
        self.countdown_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(reason_lbl)
        layout.addWidget(self.countdown_lbl)

        self.left  = 5
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

        # center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())

    def _tick(self):
        self.left -= 1
        self.countdown_lbl.setText(f"ระบบจะบังคับปิดเซสชันใน {self.left} วินาที...")
        if self.left <= 0:
            self.timer.stop()
            self.accept()


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
        self.setFixedSize(340, 140)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 360, 40)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        self.container = QFrame()
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
        inner.setContentsMargins(20, 15, 20, 15)
        inner.setSpacing(8)

        self.user_label = QLabel(f"👤  {self.email}")
        self.user_label.setStyleSheet(
            "color: #cbd5e1; font-family: 'Segoe UI'; font-size: 13px; border: none; background: transparent;"
        )

        self.status_label = QLabel("●  กำลังตรวจสอบการใช้งาน")
        self.status_label.setStyleSheet(
            "color: #22c55e; font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; border: none; background: transparent;"
        )

        self.logout_btn = QPushButton("จบการทำงาน")
        self.logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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

        inner.addWidget(self.user_label)
        inner.addWidget(self.status_label)
        inner.addWidget(self.logout_btn)
        outer.addWidget(self.container)

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

    def trigger_logout(self, reason: str = None):
        if reason:
            dlg = ViolationDialog(reason)
            dlg.exec()
        self.overlay.agent.stop_and_send_logs(self.session_id)
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
        self.focus_timer.start(1000)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def _show_error(self, msg: str):
        self.error_label.setText(f"⚠️ {msg}")
        self.error_label.show()

    def handle_login(self):
        email    = self.email_input.text().strip()
        password = self.pass_input.text()

        if not email or not password:
            self._show_error("กรุณากรอกข้อมูลให้ครบถ้วน")
            return

        self.error_label.hide()
        self.login_btn.setText("⏳ กำลังตรวจสอบ...")
        self.login_btn.setEnabled(False)

        # เก็บ email ไว้ใช้ใน callback (password ไม่เก็บ — ส่งเข้า worker แล้วจบ)
        self._login_email = email

        self._login_worker = NetworkWorker(self._do_login, email, password)
        self._login_worker.finished.connect(self._on_login_result)
        self._login_worker.error.connect(self._on_login_error)
        self._login_worker.start()

    # ── runs on WORKER thread ──
    @staticmethod
    def _do_login(email, password):
        res = post_with_retry(f"{API_URL}/login", data={"username": email, "password": password})
        if not res:
            return {"status": "connection_error"}

        if res.status_code == 200:
            session_res = post_with_retry(
                f"{API_URL}/agent/start-session",
                data={"email": email, "lab_code": LAB_CODE,
                      "device": DEVICE_HOSTNAME, "mac": DEVICE_MAC},
            )
            if session_res and session_res.status_code == 200:
                return {"status": "ok", "session_id": session_res.json()["session_id"]}
            else:
                status = session_res.status_code if session_res else "Timeout"
                text   = session_res.text if session_res else "-"
                logger.error(f"Session Error [{status}]: {text}")
                return {"status": "session_error"}
        elif res.status_code == 403:
            return {"status": "pending_approval"}
        else:
            return {"status": "invalid_credentials"}

    # ── runs on GUI thread (signal callback) ──
    def _on_login_result(self, result):
        status = result.get("status")

        if status == "ok":
            session_id = result["session_id"]
            self.is_authenticated = True
            self.focus_timer.stop()
            self.pass_input.clear()
            self.email_input.clear()
            self.hide()
            self.info_bar = SessionInfoBar(self._login_email, self, session_id)
            self.info_bar.show()
            self.agent.start_monitoring(session_id, self.info_bar)
        elif status == "connection_error":
            self._show_error("ไม่สามารถเชื่อมต่อ Server ได้ กรุณาตรวจสอบอินเทอร์เน็ต")
        elif status == "pending_approval":
            self._show_error("บัญชีนี้รอการอนุมัติจาก Admin")
        elif status == "session_error":
            self._show_error("ไม่สามารถสร้าง Session ใหม่ได้")
        else:
            self._show_error("อีเมลหรือรหัสผ่านไม่ถูกต้อง")

        self.login_btn.setText("ปลดล็อกเข้าใช้งาน")
        self.login_btn.setEnabled(True)

    def _on_login_error(self, error_msg):
        self._show_error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ: {error_msg}")
        self.login_btn.setText("ปลดล็อกเข้าใช้งาน")
        self.login_btn.setEnabled(True)


# ── SmartLabAgent ─────────────────────────────────────────────────────────────
class SmartLabAgent:
    def __init__(self):
        self.usage_stats    = {}
        self.current_session_id = None
        self.info_bar       = None
        self.overlay        = None
        self.forbidden_words = []   # โหลดจาก /admin/blacklist ตอน start_monitoring
        self.monitor_timer  = QTimer()
        self.monitor_timer.timeout.connect(self.track_usage)
        self._log_store     = PendingLogStore()
        self._flush_pending_logs()  # ส่ง logs ค้างจาก session ก่อนหน้า (ถ้ามี)

    def set_ui_references(self, overlay):
        self.overlay = overlay

    def fetch_blacklist(self):
        """โหลด blacklist จาก backend แบบ async — ใช้ fallback ระหว่างรอ"""
        self._use_fallback_blacklist()  # ใช้ fallback ก่อนเพื่อให้มี blacklist ทันที

        self._blacklist_worker = NetworkWorker(self._do_fetch_blacklist)
        self._blacklist_worker.finished.connect(self._on_blacklist_result)
        self._blacklist_worker.error.connect(
            lambda e: logger.error(f"ดึง Blacklist ไม่ได้: {e}")
        )
        self._blacklist_worker.start()

    @staticmethod
    def _do_fetch_blacklist():
        """Runs on worker thread."""
        return requests.get(f"{API_URL}/admin/blacklist", timeout=10)

    def _on_blacklist_result(self, res):
        """Runs on GUI thread — อัปเดต blacklist จาก server."""
        if res and res.status_code == 200:
            data = res.json().get("data", [])
            self.forbidden_words = [item.get("app_name", "").lower().strip() for item in data]
            logger.info(f"ดึง Blacklist สำเร็จ: {self.forbidden_words}")
        else:
            status = res.status_code if res else "No response"
            logger.warning(f"ดึง Blacklist ล้มเหลว (Status: {status}) ใช้ fallback แทน")

    def _use_fallback_blacklist(self):
        # FIX 3: fallback ต้องมีครบ รวม "star rail" และ "starrail" (ชื่อ process)
        self.forbidden_words = [
            "bittorrent", "cheatengine",
            "genshin", "genshinimpact",
            "star rail", "starrail",       # window title และ process name
        ]

    def start_monitoring(self, session_id, info_bar):
        self.current_session_id = session_id
        self.info_bar = info_bar
        self.usage_stats = {}
        self.fetch_blacklist()
        self.monitor_timer.start(5000)

    @staticmethod
    def _get_process_name_from_window(window) -> str:
        """ดึงชื่อ process (.exe) จาก active window ผ่าน Win32 API + psutil."""
        try:
            hwnd = window._hWnd
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc = psutil.Process(pid.value)
            return proc.name()          # e.g. "brave.exe", "Code.exe"
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, AttributeError):
            # fallback: parse title เดิม
            raw_title = (window.title or "").strip()
            return raw_title.split('-')[-1].strip() if '-' in raw_title else raw_title

    def track_usage(self):
        try:
            # ── ด่านที่ 1: ตรวจจากชื่อ process (.exe) ──────────────────────
            # จับเกมที่มี anti-cheat ซึ่งซ่อน window title ได้
            for proc in psutil.process_iter(['name']):
                try:
                    p_name = (proc.info['name'] or "").lower()
                    for word in self.forbidden_words:
                        if not word:
                            continue
                        if word.replace(" ", "") in p_name:
                            if self.info_bar:
                                self.info_bar.trigger_logout(reason=f"ไม่อนุญาตให้เปิดแอป: {word.title()}")
                            return
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

            # ── ด่านที่ 2: ตรวจจาก Active Window title ──────────────────────
            active_win = gw.getActiveWindow()
            if not active_win or not active_win.title:
                return

            raw_title  = active_win.title.strip()
            title_lower = raw_title.lower()

            for word in self.forbidden_words:
                if not word:
                    continue
                # FIX 4: compare ตรงๆ เช่น "star rail" in "star rail - loading" → True
                if word in title_lower:
                    if self.info_bar:
                        self.info_bar.trigger_logout(reason=f"ไม่อนุญาตให้เปิดใช้งาน: {word.title()}")
                    return

            # ── บันทึกสถิติการใช้งานปกติ ────────────────────────────────────
            # ใช้ process name จาก psutil แทนการ parse window title
            app_name = self._get_process_name_from_window(active_win)

            if app_name and app_name not in IGNORE_SYSTEM_APPS:
                self.usage_stats[app_name] = self.usage_stats.get(app_name, 0) + 5
                logger.debug(f"บันทึก: [{app_name}] สะสม {self.usage_stats[app_name]} วินาที")

        except Exception as e:
            logger.error(f"track_usage error: {e}", exc_info=True)

    def stop_and_send_logs(self, session_id):
        self.monitor_timer.stop()
        summary = [{"name": n, "duration": d} for n, d in self.usage_stats.items()]

        if not summary:
            logger.info("ไม่มีสถิติการใช้งานที่บันทึกได้")
            self._after_send_logs()
            return

        # เก็บลง local DB ก่อน — แม้ network ล้มเหลวข้อมูลไม่หาย
        try:
            row_id = self._log_store.save(
                session_id, summary,
                hostname=DEVICE_HOSTNAME, mac_address=DEVICE_MAC,
            )
        except Exception as e:
            logger.error(f"Save to local DB failed: {e}", exc_info=True)
            row_id = None

        logger.info(f"ส่งข้อมูลไป Backend — Data: {summary}")

        self._send_worker = NetworkWorker(
            self._do_send_logs, session_id, summary, DEVICE_HOSTNAME, DEVICE_MAC
        )
        self._send_worker.finished.connect(
            lambda r, rid=row_id: self._on_send_logs_done(r, rid)
        )
        self._send_worker.error.connect(
            lambda e: (logger.error(f"ส่งข้อมูลไม่ได้: {e} (เก็บไว้ใน local DB)"), self._after_send_logs())
        )
        self._send_worker.start()

    @staticmethod
    def _do_send_logs(session_id, summary, hostname="", mac=""):
        """Runs on worker thread."""
        return post_with_retry(
            f"{API_URL}/agent/log-usage",
            data={
                "session_id": session_id,
                "usage_data": json.dumps(summary),
                "device": hostname,
                "mac": mac,
            },
        )

    def _on_send_logs_done(self, r, row_id):
        """Runs on GUI thread — ลบจาก local DB ถ้าส่งสำเร็จ."""
        if r and r.status_code == 200:
            logger.info(f"Server Response: {r.status_code} — ส่งสำเร็จ")
            if row_id is not None:
                try:
                    self._log_store.delete(row_id)
                except Exception as e:
                    logger.error(f"Delete pending log failed: {e}")
        else:
            status = r.status_code if r else "Timeout"
            logger.warning(f"Server Response: {status} — เก็บไว้ใน local DB (id={row_id})")
        self._after_send_logs()

    def _flush_pending_logs(self):
        """ส่ง logs ที่ค้างส่งจาก session ก่อนหน้า (เช่น agent crash / ไฟดับ)."""
        try:
            pending = self._log_store.get_all_pending()
        except Exception as e:
            logger.error(f"Read pending logs failed: {e}")
            return

        if not pending:
            return

        logger.info(f"พบ {len(pending)} pending log(s) ค้างส่ง — กำลัง flush...")
        for row_id, session_id, usage_json, hostname, mac in pending:
            worker = NetworkWorker(
                self._do_send_logs, session_id, json.loads(usage_json),
                hostname or DEVICE_HOSTNAME, mac or DEVICE_MAC
            )
            worker.finished.connect(
                lambda r, rid=row_id: self._on_flush_done(r, rid)
            )
            worker.error.connect(
                lambda e, rid=row_id: logger.warning(f"Flush log id={rid} failed: {e}")
            )
            worker.start()
            # เก็บ ref ไว้ไม่ให้ GC ลบ thread
            if not hasattr(self, "_flush_workers"):
                self._flush_workers = []
            self._flush_workers.append(worker)

    def _on_flush_done(self, r, row_id):
        """ลบ pending log ที่ flush สำเร็จ."""
        if r and r.status_code == 200:
            logger.info(f"Flushed pending log id={row_id} successfully")
            try:
                self._log_store.delete(row_id)
            except Exception as e:
                logger.error(f"Delete flushed log id={row_id} failed: {e}")
        else:
            status = r.status_code if r else "Timeout"
            logger.warning(f"Flush log id={row_id} failed: server={status}, will retry next startup")

    def _after_send_logs(self):
        """เรียก shutdown เฉพาะเมื่อไม่ใช่ debug mode."""
        if not DEBUG_MODE:
            os.system("shutdown /l /f")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    agent_logic  = SmartLabAgent()
    login_screen = LoginOverlay(agent_logic)
    login_screen.show()
    sys.exit(app.exec())
