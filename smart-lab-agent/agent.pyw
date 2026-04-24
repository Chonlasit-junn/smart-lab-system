import sys
import os
import psutil
import json
import socket
import requests
import pygetwindow as gw
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QFrame, 
                             QGraphicsDropShadowEffect, QMessageBox)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont, QColor

# --- ⚙️ CONFIGURATION ---
API_URL = "http://localhost:8000"
LAB_CODE = "LAB01"
DEBUG_MODE = True 

# 🚨 บัญชีดำโปรแกรมต้องห้าม (เกม, บิท ฯลฯ)
FORBIDDEN_WORDS = ["Cheat", "Game", "BitTorrent", "Porn", "Star Rail", "StarRail", "Genshin"]

# 🗑️ หน้าต่างระบบที่ไม่ต้องการจดสถิติ (ป้องกันขยะล้น Database)
IGNORE_SYSTEM_APPS = ["Taskbar", "Program Manager", "Settings", "Windows Default Lock Screen", "Search"]

# --- 🚀 ส่วนที่ 1: แถบข้อมูลขวาบน (Premium UI Redesign) ---
class SessionInfoBar(QWidget):
    def __init__(self, email, overlay, session_id):
        super().__init__()
        self.email = email
        self.overlay = overlay
        self.session_id = session_id
        self.initUI()
        
    def initUI(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 📏 ปรับขนาดให้รับกับเงาและเนื้อหาพอดี
        self.setFixedSize(340, 140) 
        
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 360, 40)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(15, 23, 42, 230); 
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 30); 
            }
        """)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20); shadow.setYOffset(5); shadow.setColor(QColor(0, 0, 0, 150))
        self.container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(20, 15, 20, 15) 
        container_layout.setSpacing(8)

        self.user_label = QLabel(f"👤  {self.email}")
        self.user_label.setStyleSheet("color: #cbd5e1; font-family: 'Segoe UI', Arial; font-size: 13px; font-weight: normal; border: none; background: transparent;")
        
        self.status_label = QLabel("●  System Monitoring...")
        self.status_label.setStyleSheet("color: #22c55e; font-family: 'Segoe UI', Arial; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        
        self.logout_btn = QPushButton("Finish Session")
        self.logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444; color: white; border-radius: 8px; font-family: 'Segoe UI', Arial;
                font-size: 13px; font-weight: bold; padding: 8px; border: none; margin-top: 4px;
            }
            QPushButton:hover { background-color: #f87171; }
            QPushButton:pressed { background-color: #b91c1c; }
        """)
        self.logout_btn.clicked.connect(self.handle_logout_click)

        container_layout.addWidget(self.user_label)
        container_layout.addWidget(self.status_label)
        container_layout.addWidget(self.logout_btn)
        
        layout.addWidget(self.container)

    def handle_logout_click(self):
        msg = QMessageBox(self.overlay)
        msg.setWindowTitle("Confirm Exit")
        msg.setText("จบการใช้งานและบันทึกสถิติ?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setStyleSheet("QPushButton { padding: 6px 15px; border-radius: 5px; font-weight: bold; } QLabel { font-size: 13px; }")
        if msg.exec() == QMessageBox.StandardButton.Yes:
            self.trigger_logout()

    def trigger_logout(self, reason=None):
        self.overlay.agent.stop_and_send_logs(self.session_id)
        self.hide()
        self.overlay.reset_and_show()
        if reason:
            msg = QMessageBox(self.overlay) 
            msg.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText("Violation Detected")
            msg.setInformativeText(f"สาเหตุ: {reason}")
            msg.setStyleSheet("QPushButton { padding: 6px 15px; border-radius: 5px; font-weight: bold; } QLabel { font-size: 13px; font-weight: bold; color: #1e293b; }")
            msg.exec()

# --- 🔒 ส่วนที่ 2: หน้าจอ Lock Screen ---
class LoginOverlay(QWidget):
    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        self.agent.set_ui_references(self)
        self.is_authenticated = False 
        self.initUI()
        
        self.focus_timer = QTimer()
        self.focus_timer.timeout.connect(self.lock_focus)
        self.focus_timer.start(1000)

    def initUI(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setGeometry(QApplication.primaryScreen().geometry()) 
        self.setStyleSheet("background-color: #0f172a;")

        main_layout = QVBoxLayout(self)
        main_layout.addStretch()
        h_layout = QHBoxLayout(); h_layout.addStretch()

        self.card = QFrame()
        self.card.setFixedSize(450, 550)
        self.card.setStyleSheet("background-color: #ffffff; border-radius: 25px;")
        
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(45, 45, 45, 45)

        title = QLabel("Smart Lab Access")
        title.setFont(QFont("Inter", 24, QFont.Weight.Bold))
        title.setStyleSheet("color: #1e293b; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        card_layout.addWidget(QLabel("Email", styleSheet="color: #475569; font-weight: bold; margin-top: 20px; border: none;"))
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("name@example.com")
        self.email_input.setStyleSheet("""
            QLineEdit {
                padding: 12px; border: 2px solid #e2e8f0; border-radius: 10px; 
                font-size: 16px; color: #1e293b; background-color: #f8fafc;
            }
            QLineEdit:focus { border: 2px solid #3b82f6; background-color: #ffffff; }
        """)
        card_layout.addWidget(self.email_input)

        card_layout.addWidget(QLabel("Password", styleSheet="color: #475569; font-weight: bold; margin-top: 15px; border: none;"))
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setStyleSheet(self.email_input.styleSheet())
        card_layout.addWidget(self.pass_input)

        self.login_btn = QPushButton("Unlock System")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setStyleSheet("background-color: #2563eb; color: white; padding: 15px; border-radius: 10px; font-weight: bold; margin-top: 35px; border: none;")
        self.login_btn.clicked.connect(self.handle_login)
        card_layout.addWidget(self.login_btn)

        h_layout.addWidget(self.card); h_layout.addStretch()
        main_layout.addLayout(h_layout); main_layout.addStretch()

    def lock_focus(self):
        if not self.is_authenticated:
            if not self.isFullScreen(): self.showFullScreen()
            self.raise_(); self.activateWindow()

    def reset_and_show(self):
        self.is_authenticated = False
        self.email_input.clear(); self.pass_input.clear()
        self.showFullScreen(); self.raise_(); self.activateWindow()

    def handle_login(self):
        email, password = self.email_input.text(), self.pass_input.text()
        try:
            res = requests.post(f"{API_URL}/login", data={"username": email, "password": password})
            if res.status_code == 200:
                device_name = socket.gethostname()
                session_res = requests.post(f"{API_URL}/agent/start-session", data={"email": email, "lab_code": LAB_CODE, "device": device_name})
                if session_res.status_code == 200:
                    session_id = session_res.json()["session_id"]
                    self.is_authenticated = True
                    self.hide()
                    self.info_bar = SessionInfoBar(email, self, session_id)
                    self.info_bar.show()
                    self.agent.start_monitoring(session_id, self.info_bar)
            else:
                QMessageBox.warning(self, "Error", "อีเมลหรือรหัสผ่านไม่ถูกต้อง")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"เชื่อมต่อไม่ได้: {e}")

# --- 🕵️ ส่วนที่ 3: ระบบ Monitoring (No Whitelist Version) ---
class SmartLabAgent:
    def __init__(self):
        self.usage_stats = {}
        self.current_session_id = None
        self.info_bar = None
        self.overlay = None
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.track_usage)

    def set_ui_references(self, overlay):
        self.overlay = overlay

    def start_monitoring(self, session_id, info_bar):
        self.current_session_id = session_id
        self.info_bar = info_bar
        self.usage_stats = {}
        self.monitor_timer.start(5000) # เช็กทุก 5 วินาที

    def track_usage(self):
        try:
            active_win = gw.getActiveWindow()
            if not active_win or not active_win.title: return
            
            raw_title = active_win.title.strip()

            # 🚨 1. ตรวจจับเกมก่อนเป็นอันดับแรก
            for word in FORBIDDEN_WORDS:
                if word.lower() in raw_title.lower():
                    if self.info_bar:
                        self.info_bar.trigger_logout(reason=f"ไม่อนุญาตให้เปิดใช้งาน {word}")
                    return 
            
            # 📝 2. โหมดดึงชื่อโปรแกรมแบบอัตโนมัติ (สกัดคำขยะออก)
            # ตัวอย่าง: "Google - Brave" -> จะเหลือแค่ "Brave"
            if '-' in raw_title:
                app_name = raw_title.split('-')[-1].strip()
            else:
                app_name = raw_title

            # กรองหน้าต่างระบบทิ้งไป
            if app_name and app_name not in IGNORE_SYSTEM_APPS:
                self.usage_stats[app_name] = self.usage_stats.get(app_name, 0) + 5
                print(f"⏱️ บันทึกสถิติ: [{app_name}] -> สะสม {self.usage_stats[app_name]} วินาที")

        except Exception as e: pass

    def stop_and_send_logs(self, session_id):
        self.monitor_timer.stop()
        summary = [{"name": n, "duration": d} for n, d in self.usage_stats.items()]
        
        print(f"\n--- 📤 SENDING DATA TO BACKEND ---")
        print(f"Data: {summary}")
        
        if summary:
            try:
                r = requests.post(f"{API_URL}/agent/log-usage", data={"session_id": session_id, "usage_data": json.dumps(summary)})
                print(f"✅ Server Response: {r.status_code}")
            except Exception as e: print(f"❌ Failed to send: {e}")
        else:
            print("⚠️ No valid app activity recorded.")

        if not DEBUG_MODE: os.system("shutdown /l /f")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    agent_logic = SmartLabAgent()
    login_screen = LoginOverlay(agent_logic)
    login_screen.show()
    sys.exit(app.exec())