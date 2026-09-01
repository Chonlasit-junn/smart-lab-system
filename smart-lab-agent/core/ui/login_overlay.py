from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from ..config import API_URL, LAB_CODE, DEVICE_HOSTNAME, DEVICE_MAC
from ..network import NetworkWorker, post_with_retry
from .session_bar import SessionInfoBar
from ..logger import logger

class LoginOverlay(QWidget):
    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        # ไม่ต้อง set_ui_references เพราะใช้ Event-driven pyqtSignal แล้ว
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
            self.agent.start_monitoring(session_id)
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
