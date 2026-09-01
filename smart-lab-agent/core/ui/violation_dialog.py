from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

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

        sub = QLabel("ระบบกำลังบันทึกสถิติและล็อกเอาท์อัตโนมัติ...")
        sub.setFont(QFont("Segoe UI", 12))
        sub.setStyleSheet("color: #991b1b; margin-top: 20px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(reason_lbl)
        layout.addStretch()
        layout.addWidget(sub)
