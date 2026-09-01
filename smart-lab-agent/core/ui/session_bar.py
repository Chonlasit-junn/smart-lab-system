from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, 
                             QGraphicsDropShadowEffect, QApplication, QDialog)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from .violation_dialog import ViolationDialog

class SessionInfoBar(QWidget):
    def __init__(self, email: str, overlay, session_id: str):
        super().__init__()
        self.email = email
        self.overlay = overlay
        self.session_id = session_id
        
        # เชื่อมต่อสัญญาณจาก SmartLabAgent
        self.overlay.agent.violation_detected.connect(self.trigger_logout)

        self._init_ui()

        # Update position timer
        self.pos_timer = QTimer(self)
        self.pos_timer.timeout.connect(self._keep_centered)
        self.pos_timer.start(500)

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(500, 70)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        bg = QWidget()
        bg.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 0.95);
                border-radius: 25px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        bg.setGraphicsEffect(shadow)

        layout = QHBoxLayout(bg)
        layout.setContentsMargins(20, 0, 20, 0)

        # Status dot
        dot = QLabel("●")
        dot.setStyleSheet("color: #22c55e; font-size: 18px; border: none; background: transparent;")
        
        # Email text
        email_lbl = QLabel(f"กำลังใช้งาน: {self.email}")
        email_lbl.setFont(QFont("Segoe UI", 12))
        email_lbl.setStyleSheet("color: #f1f5f9; border: none; background: transparent;")

        # Logout button
        logout_btn = QPushButton("จบการใช้งาน")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444; color: white; border-radius: 12px;
                font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
                padding: 8px 15px; border: none;
            }
            QPushButton:hover { background-color: #f87171; }
        """)
        logout_btn.clicked.connect(self._confirm_logout)

        layout.addWidget(dot)
        layout.addWidget(email_lbl)
        layout.addStretch()
        layout.addWidget(logout_btn)

        main_layout.addWidget(bg)
        self._keep_centered()

    def _keep_centered(self):
        screen = QApplication.primaryScreen().geometry()
        x = screen.center().x() - (self.width() // 2)
        y = 20  # ห่างจากขอบบน 20px
        self.move(x, y)

    def _confirm_logout(self):
        dlg = QDialog(self)
        dlg.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog
        )
        dlg.setStyleSheet("""
            QDialog { background-color: #1e293b; border-radius: 15px; border: 1px solid #334155; }
        """)
        dlg.setFixedSize(300, 150)

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
            
        # disconnect เพื่อกัน signal firing ซ้ำตอน logout
        try:
            self.overlay.agent.violation_detected.disconnect(self.trigger_logout)
        except TypeError:
            pass

        self.overlay.agent.stop_and_send_logs(self.session_id)
        self.hide()
        self.overlay.reset_and_show()
