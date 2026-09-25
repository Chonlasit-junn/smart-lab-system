"""Desktop wizard for assigning this workstation to a Smart Lab.

The wizard uses the existing Admin and device-registration APIs, so a
technician can provision a workstation without opening the Admin website.
Admin credentials and access tokens stay in memory and are never written to
the workstation. Only the device credential returned by the Backend is saved
for the Agent.
"""

from __future__ import annotations

import argparse
import getpass
import os
import platform
import sys
import threading
from typing import Any, Callable, Optional

import requests

from agent_device import load_device_registration, save_device_registration
from device_registration import (
    DEFAULT_AGENT_VERSION,
    DEFAULT_API_URL,
    LabSetupError,
    build_device_payload_for_api,
    normalize_api_url,
    register_device_as_admin,
)


def _response_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:300]

    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message")
        if isinstance(detail, (dict, list)):
            return str(detail)
        return str(detail or "").strip()
    return ""


def _raise_for_api_error(response: requests.Response, expected: set[int]) -> None:
    if response.status_code in expected:
        return
    detail = _response_detail(response) or f"HTTP {response.status_code}"
    raise LabSetupError(detail)


def login_admin(
    api_url: str,
    email: str,
    password: str,
    *,
    client: Any = requests,
    timeout: int = 20,
) -> str:
    """Authenticate an administrator and return a short-lived access token."""

    try:
        response = client.post(
            f"{normalize_api_url(api_url)}/login",
            data={"username": email.strip(), "password": password},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise LabSetupError(f"เชื่อมต่อ Backend ไม่สำเร็จ: {exc}") from exc

    _raise_for_api_error(response, {200})
    try:
        token = str(response.json().get("access_token") or "").strip()
    except (AttributeError, ValueError):
        token = ""
    if not token:
        raise LabSetupError("Backend ไม่ได้ส่ง access token กลับมา")
    return token


def list_active_labs(
    api_url: str,
    access_token: str,
    *,
    client: Any = requests,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """Return active Labs in a stable, UI-friendly order."""

    try:
        response = client.get(
            f"{normalize_api_url(api_url)}/labs",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise LabSetupError(f"ดึงรายชื่อ Lab ไม่สำเร็จ: {exc}") from exc

    _raise_for_api_error(response, {200})
    try:
        rows = response.json().get("data", [])
    except (AttributeError, ValueError):
        rows = []
    if not isinstance(rows, list):
        raise LabSetupError("รูปแบบข้อมูล Lab จาก Backend ไม่ถูกต้อง")

    active_labs = [
        row
        for row in rows
        if isinstance(row, dict) and str(row.get("status") or "").lower() == "active"
    ]
    return sorted(active_labs, key=lambda row: str(row.get("code") or ""))


class LabSetupApp:
    """Small Tkinter UI kept dependency-free for the setup workstation."""

    def __init__(self, root: Any, api_url: str, device_name: str) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.root.title("Smart Lab - Register This Computer")
        self.root.geometry("560x390")
        self.root.resizable(False, False)

        self.admin_token: Optional[str] = None
        self.labs: list[dict[str, Any]] = []

        self.api_url_var = tk.StringVar(value=api_url)
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.device_name_var = tk.StringVar(value=device_name)
        self.lab_var = tk.StringVar()
        self.status_var = tk.StringVar(value="กรอกข้อมูล Admin แล้วกด ‘โหลดรายชื่อ Lab’")

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        title = ttk.Label(frame, text="ลงทะเบียนคอมพิวเตอร์เข้า Lab", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        subtitle = ttk.Label(
            frame,
            text="ใช้สำหรับติดตั้งครั้งแรกเท่านั้น ไม่บันทึกรหัสผ่าน Admin ลงเครื่อง",
        )
        subtitle.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 18))

        self._field(frame, 2, "Backend URL", self.api_url_var)
        self._field(frame, 3, "Admin Email", self.email_var)
        self.password_entry = self._field(frame, 4, "Admin Password", self.password_var, show="*")
        self._field(frame, 5, "ชื่อเครื่อง", self.device_name_var)

        ttk.Label(frame, text="Lab").grid(row=6, column=0, sticky="w", pady=6)
        self.lab_combo = ttk.Combobox(frame, textvariable=self.lab_var, state="readonly", width=42)
        self.lab_combo.grid(row=6, column=1, sticky="ew", pady=6)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=7, column=0, columnspan=2, sticky="e", pady=(16, 8))
        self.load_button = ttk.Button(button_frame, text="โหลดรายชื่อ Lab", command=self.load_labs)
        self.load_button.pack(side="left", padx=(0, 8))
        self.register_button = ttk.Button(
            button_frame,
            text="ลงทะเบียนเครื่อง",
            command=self.register_device,
            state="disabled",
        )
        self.register_button.pack(side="left")

        self.status_label = ttk.Label(frame, textvariable=self.status_var, wraplength=500)
        self.status_label.grid(row=8, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _field(
        self,
        parent: Any,
        row: int,
        label: str,
        variable: Any,
        show: Optional[str] = None,
    ) -> Any:
        self.ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        entry = self.ttk.Entry(parent, textvariable=variable, width=45, show=show or "")
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        return entry

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.load_button.configure(state=state)
        self.register_button.configure(state="disabled" if busy or not self.labs else "normal")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _run_async(self, operation: Callable[[], Any], on_success: Callable[[Any], None]) -> None:
        self._set_busy(True)

        def worker() -> None:
            try:
                result = operation()
            except Exception as exc:  # Keep network errors inside the wizard.
                self.root.after(0, lambda error=exc: self._operation_failed(error))
            else:
                self.root.after(0, lambda value=result: self._operation_succeeded(on_success, value))

        threading.Thread(target=worker, daemon=True).start()

    def _operation_failed(self, error: Exception) -> None:
        self._set_busy(False)
        self._set_status(f"ไม่สำเร็จ: {error}")
        self.messagebox.showerror("ลงทะเบียนไม่สำเร็จ", str(error), parent=self.root)

    def _operation_succeeded(self, callback: Callable[[Any], None], result: Any) -> None:
        self._set_busy(False)
        callback(result)

    def load_labs(self) -> None:
        api_url = self.api_url_var.get().strip()
        email = self.email_var.get().strip()
        password = self.password_var.get()
        if not api_url or not email or not password:
            self._set_status("กรุณากรอก Backend URL, Admin Email และรหัสผ่าน")
            return

        self.admin_token = None
        self.labs = []
        self.lab_combo["values"] = ()
        self.lab_var.set("")
        self.register_button.configure(state="disabled")
        self._set_status("กำลังตรวจสอบ Admin และโหลดรายชื่อ Lab...")

        def operation() -> tuple[str, list[dict[str, Any]]]:
            token = login_admin(api_url, email, password)
            return token, list_active_labs(api_url, token)

        def completed(result: tuple[str, list[dict[str, Any]]]) -> None:
            self.admin_token, self.labs = result
            self.password_var.set("")
            self.lab_combo["values"] = [
                f"{lab.get('code', '-') } — {lab.get('name', '-') }" for lab in self.labs
            ]
            if self.labs:
                self.lab_combo.current(0)
                self.register_button.configure(state="normal")
                self._set_status(f"พบ {len(self.labs)} Lab ที่พร้อมใช้งาน เลือก Lab แล้วลงทะเบียนได้")
            else:
                self._set_status("ไม่พบ Lab ที่มีสถานะ active")

        self._run_async(operation, completed)

    def register_device(self) -> None:
        if not self.admin_token or not self.labs:
            self._set_status("กรุณาโหลดรายชื่อ Lab ก่อน")
            return

        selected_index = self.lab_combo.current()
        if selected_index < 0 or selected_index >= len(self.labs):
            self._set_status("กรุณาเลือก Lab")
            return

        api_url = self.api_url_var.get().strip()
        access_token = self.admin_token
        lab_id = int(self.labs[selected_index]["id"])
        device_name = self.device_name_var.get().strip()

        def operation() -> tuple[dict[str, Any], Any]:
            payload = build_device_payload_for_api(
                load_device_registration(),
                api_url,
                device_name,
            )
            registration = register_device_as_admin(
                api_url,
                access_token,
                lab_id,
                payload,
            )
            path = save_device_registration(registration)
            return registration, path

        def completed(result: tuple[dict[str, Any], Any]) -> None:
            registration, path = result
            self.admin_token = None
            self.password_var.set("")
            self._set_status(
                f"ลงทะเบียนสำเร็จ: {registration.get('lab_code')} — "
                f"บันทึก Credential ที่ {path}"
            )
            self.messagebox.showinfo(
                "ลงทะเบียนสำเร็จ",
                "ลงทะเบียนเครื่องเรียบร้อยแล้ว\nปิดแล้วเปิด Agent ใหม่ก่อนใช้งาน",
                parent=self.root,
            )

        self._set_status("กำลังลงทะเบียนเครื่องกับ Lab...")
        self._run_async(operation, completed)


def launch_qt(api_url: str, device_name: str) -> int:
    """Launch the real desktop UI using the Agent's existing PyQt6 runtime."""

    try:
        from PyQt6.QtCore import QObject, QThread, pyqtSignal
        from PyQt6.QtWidgets import (
            QApplication,
            QComboBox,
            QFormLayout,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPushButton,
            QScrollArea,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        print(
            f"PyQt6 is unavailable ({exc}). Install smart-lab-agent/requirements.txt "
            "or run: python lab_setup.py --cli",
            file=sys.stderr,
        )
        return 1

    class SetupWorker(QObject):
        finished = pyqtSignal(object)
        failed = pyqtSignal(str)

        def __init__(self, operation: Callable[[], Any]) -> None:
            super().__init__()
            self.operation: Optional[Callable[[], Any]] = operation

        def run(self) -> None:
            operation = self.operation
            self.operation = None
            if operation is None:
                return
            try:
                self.finished.emit(operation())
            except Exception as exc:  # Keep errors inside the UI.
                self.failed.emit(str(exc))
            finally:
                operation = None

    class LabSetupWindow(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setObjectName("setupWindow")
            self.setWindowTitle("Smart Lab - Register This Computer")
            self.setMinimumSize(720, 620)
            self.resize(760, 660)

            self.admin_token: Optional[str] = None
            self.labs: list[dict[str, Any]] = []
            self.worker_thread: Optional[QThread] = None
            self.worker: Optional[SetupWorker] = None
            self.success_callback: Optional[Callable[[Any], None]] = None

            outer_layout = QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)

            scroll_area = QScrollArea()
            scroll_area.setObjectName("contentScroll")
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            content = QWidget()
            content.setObjectName("setupContent")
            scroll_area.setWidget(content)
            outer_layout.addWidget(scroll_area)

            layout = QVBoxLayout(content)
            layout.setContentsMargins(34, 30, 34, 30)
            layout.setSpacing(16)

            hero = QFrame()
            hero.setObjectName("hero")
            hero_layout = QVBoxLayout(hero)
            hero_layout.setContentsMargins(26, 22, 26, 22)
            hero_layout.setSpacing(6)
            eyebrow = QLabel("SMART LAB  /  WORKSTATION SETUP")
            eyebrow.setObjectName("eyebrow")
            hero_layout.addWidget(eyebrow)
            title = QLabel("ลงทะเบียนคอมพิวเตอร์เข้า Lab")
            title.setObjectName("heroTitle")
            hero_layout.addWidget(title)
            subtitle = QLabel(
                "ตั้งค่าเครื่องนี้เพียงครั้งเดียว แล้ว Agent จะรู้ว่าเครื่องอยู่ Lab ใด"
            )
            subtitle.setObjectName("heroSubtitle")
            subtitle.setWordWrap(True)
            hero_layout.addWidget(subtitle)
            layout.addWidget(hero)

            step_strip = QFrame()
            step_strip.setObjectName("stepStrip")
            steps_layout = QHBoxLayout(step_strip)
            steps_layout.setContentsMargins(0, 0, 0, 0)
            steps_layout.setSpacing(10)
            for number, name, description in (
                ("01", "ยืนยันตัวตน", "ใช้บัญชี Admin"),
                ("02", "เลือก Lab", "เลือกห้องที่ติดตั้ง"),
                ("03", "ลงทะเบียน", "บันทึก Credential"),
            ):
                step = QFrame()
                step.setObjectName("stepCard")
                step.setProperty("active", number == "01")
                step_layout = QVBoxLayout(step)
                step_layout.setContentsMargins(14, 12, 14, 12)
                step_layout.setSpacing(2)
                number_label = QLabel(number)
                number_label.setObjectName("stepNumber")
                step_layout.addWidget(number_label)
                name_label = QLabel(name)
                name_label.setObjectName("stepName")
                step_layout.addWidget(name_label)
                description_label = QLabel(description)
                description_label.setObjectName("stepDescription")
                step_layout.addWidget(description_label)
                steps_layout.addWidget(step, 1)
            layout.addWidget(step_strip)

            form_card = QFrame()
            form_card.setObjectName("formCard")
            card_layout = QVBoxLayout(form_card)
            card_layout.setContentsMargins(24, 22, 24, 22)
            card_layout.setSpacing(14)

            form_header = QHBoxLayout()
            section_title = QLabel("ข้อมูลการติดตั้ง")
            section_title.setObjectName("sectionTitle")
            form_header.addWidget(section_title)
            form_header.addStretch(1)
            admin_badge = QLabel("ADMIN ONLY")
            admin_badge.setObjectName("badge")
            form_header.addWidget(admin_badge)
            card_layout.addLayout(form_header)

            form_hint = QLabel("กรอกข้อมูลเพื่อเชื่อมต่อ Backend และเลือกระบุ Lab ของเครื่องนี้")
            form_hint.setObjectName("formHint")
            card_layout.addWidget(form_hint)

            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
            form.setHorizontalSpacing(18)
            form.setVerticalSpacing(12)

            self.api_edit = QLineEdit(api_url)
            self.api_edit.setPlaceholderText("https://backend.example.com")
            self.email_edit = QLineEdit()
            self.email_edit.setPlaceholderText("admin@example.com")
            self.password_edit = QLineEdit()
            self.password_edit.setPlaceholderText("รหัสผ่าน Admin")
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.device_name_edit = QLineEdit(device_name)
            self.device_name_edit.setPlaceholderText("เช่น LAB-A-01")
            self.lab_combo = QComboBox()
            self.lab_combo.setMinimumHeight(40)
            self.lab_combo.setMaxVisibleItems(8)
            self.lab_combo.setToolTip("เลือก Lab ที่ติดตั้งเครื่องนี้")
            self.lab_combo.addItem("กด ‘โหลดรายชื่อ Lab’ ก่อน")
            self.lab_combo.setItemData(0, None, Qt.ItemDataRole.UserRole)
            self.lab_combo.setEnabled(False)

            form.addRow("Backend URL", self.api_edit)
            form.addRow("Admin Email", self.email_edit)
            form.addRow("Admin Password", self.password_edit)
            form.addRow("ชื่อเครื่อง", self.device_name_edit)
            form.addRow("Lab ที่ติดตั้ง", self.lab_combo)
            card_layout.addLayout(form)
            layout.addWidget(form_card)

            action_layout = QHBoxLayout()
            action_layout.setSpacing(10)
            action_layout.addStretch(1)
            self.load_button = QPushButton("↻  โหลดรายชื่อ Lab")
            self.load_button.setObjectName("secondaryButton")
            self.register_button = QPushButton("ลงทะเบียนเครื่อง  →")
            self.register_button.setObjectName("primaryButton")
            self.register_button.setEnabled(False)
            action_layout.addWidget(self.load_button)
            action_layout.addWidget(self.register_button)
            layout.addLayout(action_layout)

            status_card = QFrame()
            status_card.setObjectName("statusCard")
            status_layout = QHBoxLayout(status_card)
            status_layout.setContentsMargins(14, 11, 14, 11)
            status_layout.setSpacing(10)
            self.status_icon = QLabel("i")
            self.status_icon.setObjectName("statusIcon")
            self.status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.status_icon.setFixedSize(24, 24)
            status_layout.addWidget(self.status_icon)
            self.status_label = QLabel("กรอกข้อมูล Admin แล้วกด ‘โหลดรายชื่อ Lab’")
            self.status_label.setObjectName("statusText")
            self.status_label.setWordWrap(True)
            status_layout.addWidget(self.status_label, 1)
            layout.addWidget(status_card)
            self.status_card = status_card

            footer = QLabel(
                "ความปลอดภัย: รหัสผ่านและ Access Token จะอยู่ในหน่วยความจำเท่านั้น "
                "ระบบจะบันทึกเฉพาะ Device Credential ของเครื่องนี้"
            )
            footer.setObjectName("footerNote")
            footer.setWordWrap(True)
            layout.addWidget(footer)
            layout.addStretch(1)

            self.load_button.clicked.connect(self.load_labs)
            self.register_button.clicked.connect(self.register_device)

        def set_status(self, text: str, error: bool = False) -> None:
            color = "#b91c1c" if error else "#166534" if "สำเร็จ" in text else "#1d4ed8"
            background = "#fef2f2" if error else "#f0fdf4" if "สำเร็จ" in text else "#eff6ff"
            border = "#fecaca" if error else "#bbf7d0" if "สำเร็จ" in text else "#bfdbfe"
            icon = "!" if error else "✓" if "สำเร็จ" in text else "i"
            self.status_card.setStyleSheet(
                "QFrame#statusCard { "
                f"background-color: {background}; border: 1px solid {border}; "
                "border-radius: 10px; }"
            )
            self.status_icon.setText(icon)
            self.status_icon.setStyleSheet(
                f"color: {color}; background-color: transparent; font-weight: 700;"
            )
            self.status_label.setStyleSheet(f"color: {color};")
            self.status_label.setText(text)

        def set_busy(self, busy: bool) -> None:
            self.load_button.setEnabled(not busy)
            can_select_lab = not busy and bool(self.labs) and bool(self.admin_token)
            self.register_button.setEnabled(can_select_lab)
            self.lab_combo.setEnabled(can_select_lab)

        def run_async(self, operation: Callable[[], Any], callback: Callable[[Any], None]) -> None:
            self.set_busy(True)
            self.success_callback = callback
            self.worker_thread = QThread(self)
            self.worker = SetupWorker(operation)
            self.worker.moveToThread(self.worker_thread)
            self.worker_thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.worker_succeeded)
            self.worker.failed.connect(self.worker_failed)
            self.worker.finished.connect(self.worker_thread.quit)
            self.worker.failed.connect(self.worker_thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.failed.connect(self.worker.deleteLater)
            self.worker_thread.finished.connect(self.worker_thread.deleteLater)
            self.worker_thread.start()

        def worker_succeeded(self, result: Any) -> None:
            self.set_busy(False)
            callback = self.success_callback
            self.success_callback = None
            if callback:
                callback(result)

        def worker_failed(self, error: str) -> None:
            self.set_busy(False)
            self.success_callback = None
            self.set_status(f"ไม่สำเร็จ: {error}", error=True)
            QMessageBox.critical(self, "ลงทะเบียนไม่สำเร็จ", error)

        def load_labs(self) -> None:
            api_url_value = self.api_edit.text().strip()
            email = self.email_edit.text().strip()
            password = self.password_edit.text()
            if not api_url_value or not email or not password:
                self.set_status("กรุณากรอก Backend URL, Admin Email และรหัสผ่าน", error=True)
                return

            self.admin_token = None
            self.labs = []
            self.lab_combo.clear()
            self.lab_combo.addItem("กำลังโหลดรายชื่อ Lab...")
            self.lab_combo.setItemData(0, None, Qt.ItemDataRole.UserRole)
            self.lab_combo.setEnabled(False)
            self.register_button.setEnabled(False)
            self.set_status("กำลังตรวจสอบ Admin และโหลดรายชื่อ Lab...")

            def operation() -> tuple[str, list[dict[str, Any]]]:
                token = login_admin(api_url_value, email, password)
                return token, list_active_labs(api_url_value, token)

            def completed(result: tuple[str, list[dict[str, Any]]]) -> None:
                self.admin_token, self.labs = result
                self.password_edit.clear()
                self.lab_combo.clear()
                if self.labs:
                    for lab in self.labs:
                        code = str(lab.get("code") or "-").strip()
                        name = str(lab.get("name") or "ไม่ระบุชื่อ Lab").strip()
                        location = str(lab.get("location") or "").strip()
                        label = f"{code}  —  {name}"
                        if location:
                            label += f"  ·  {location}"
                        self.lab_combo.addItem(label, int(lab["id"]))
                    self.lab_combo.setCurrentIndex(0)
                    self.lab_combo.setEnabled(True)
                    self.register_button.setEnabled(True)
                    self.set_status(
                        f"พบ {len(self.labs)} Lab ที่พร้อมใช้งาน เลือก Lab แล้วลงทะเบียนได้"
                    )
                else:
                    self.lab_combo.addItem("ไม่พบ Lab ที่มีสถานะ active")
                    self.lab_combo.setItemData(0, None, Qt.ItemDataRole.UserRole)
                    self.lab_combo.setEnabled(False)
                    self.set_status("ไม่พบ Lab ที่มีสถานะ active", error=True)

            self.run_async(operation, completed)

        def register_device(self) -> None:
            if not self.admin_token or not self.labs:
                self.set_status("กรุณาโหลดรายชื่อ Lab ก่อน", error=True)
                return

            selected_lab_id = self.lab_combo.currentData(Qt.ItemDataRole.UserRole)
            if selected_lab_id is None:
                self.set_status("กรุณาเลือก Lab", error=True)
                return

            api_url_value = self.api_edit.text().strip()
            access_token = self.admin_token
            lab_id = int(selected_lab_id)
            selected_device_name = self.device_name_edit.text().strip()

            def operation() -> tuple[dict[str, Any], Any]:
                payload = build_device_payload_for_api(
                    load_device_registration(),
                    api_url_value,
                    selected_device_name,
                )
                registration = register_device_as_admin(
                    api_url_value,
                    access_token,
                    lab_id,
                    payload,
                )
                path = save_device_registration(registration)
                return registration, path

            def completed(result: tuple[dict[str, Any], Any]) -> None:
                registration, path = result
                self.admin_token = None
                self.password_edit.clear()
                self.register_button.setEnabled(False)
                self.lab_combo.setEnabled(False)
                self.set_status(
                    f"ลงทะเบียนสำเร็จ: {registration.get('lab_code')} — "
                    f"บันทึก Credential ที่ {path}"
                )
                QMessageBox.information(
                    self,
                    "ลงทะเบียนสำเร็จ",
                    "ลงทะเบียนเครื่องเรียบร้อยแล้ว\nปิดแล้วเปิด Agent ใหม่ก่อนใช้งาน",
                )

            self.set_status("กำลังลงทะเบียนเครื่องกับ Lab...")
            self.run_async(operation, completed)

    from PyQt6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(
        """
        QWidget#setupWindow { background-color: #f4f7fb; color: #0f172a; }
        QScrollArea#contentScroll { background-color: #f4f7fb; border: none; }
        QWidget#setupContent { background-color: #f4f7fb; }
        QScrollBar:vertical { background: #e8eef6; width: 9px; margin: 4px 2px 4px 0; border-radius: 4px; }
        QScrollBar::handle:vertical { background: #b6c7dc; min-height: 36px; border-radius: 4px; }
        QScrollBar::handle:vertical:hover { background: #8eabc8; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QLabel { color: #0f172a; font-family: 'Segoe UI'; font-size: 10pt; }
        QFrame#hero { background-color: #102a43; border-radius: 18px; }
        QLabel#eyebrow { color: #9ec5e8; font-size: 9pt; font-weight: 700; letter-spacing: 1px; }
        QLabel#heroTitle { color: #ffffff; font-size: 22px; font-weight: 700; }
        QLabel#heroSubtitle { color: #c9ddf0; font-size: 10pt; }
        QFrame#stepCard { background-color: #e8eef6; border: 1px solid #d8e2ef; border-radius: 11px; }
        QFrame#stepCard[active="true"] { background-color: #e5f0ff; border: 1px solid #9fc5f5; }
        QLabel#stepNumber { color: #3478b9; font-size: 9pt; font-weight: 700; }
        QLabel#stepName { color: #16324f; font-size: 10pt; font-weight: 700; }
        QLabel#stepDescription { color: #64748b; font-size: 9pt; }
        QFrame#formCard { background-color: #ffffff; border: 1px solid #dfe7f0; border-radius: 16px; }
        QLabel#sectionTitle { color: #102a43; font-size: 14pt; font-weight: 700; }
        QLabel#formHint { color: #64748b; }
        QLabel#badge { color: #2563eb; background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px; padding: 4px 9px; font-size: 8pt; font-weight: 700; }
        QLineEdit, QComboBox { background-color: #f8fafc; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 8px; padding: 9px 11px; min-height: 20px; }
        QLineEdit:focus, QComboBox:focus { background-color: #ffffff; border: 2px solid #60a5fa; padding: 8px 10px; }
        QLineEdit:disabled, QComboBox:disabled { color: #94a3b8; background-color: #f1f5f9; }
        QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 34px; border: none; }
        QComboBox QAbstractItemView { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; selection-background-color: #dbeafe; selection-color: #1e3a8a; padding: 4px; outline: none; }
        QComboBox QAbstractItemView::item { min-height: 32px; padding: 7px 10px; }
        QPushButton { min-height: 22px; border-radius: 8px; padding: 9px 16px; font-weight: 700; }
        QPushButton#secondaryButton { color: #1e40af; background-color: #ffffff; border: 1px solid #bfdbfe; }
        QPushButton#secondaryButton:hover { background-color: #eff6ff; }
        QPushButton#primaryButton { color: #ffffff; background-color: #2563eb; border: 1px solid #2563eb; }
        QPushButton#primaryButton:hover { background-color: #1d4ed8; }
        QPushButton:disabled { color: #94a3b8; background-color: #e2e8f0; border: 1px solid #e2e8f0; }
        QFrame#statusCard { background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px; }
        QLabel#statusIcon { color: #1d4ed8; background-color: transparent; font-size: 12pt; font-weight: 700; }
        QLabel#statusText { color: #1d4ed8; }
        QLabel#footerNote { color: #64748b; font-size: 9pt; }
        """
    )
    window = LabSetupWindow()
    window.show()
    return app.exec()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register this workstation to a Smart Lab without the Admin website.")
    parser.add_argument(
        "--api-url",
        default=os.getenv("SMART_LAB_API_URL", DEFAULT_API_URL),
        help="Smart Lab Backend URL",
    )
    parser.add_argument(
        "--device-name",
        default=platform.node() or "Smart Lab workstation",
        help="Display name for this workstation",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Use the terminal wizard when Tkinter is unavailable",
    )
    return parser.parse_args()


def run_cli(api_url: str, device_name: str) -> int:
    """Fallback wizard for Python installations without Tcl/Tk."""

    print("Smart Lab - Register This Computer")
    print("รหัสผ่าน Admin จะไม่ถูกบันทึกลงเครื่อง\n")
    email = input("Admin Email: ").strip()
    password = getpass.getpass("Admin Password: ")

    try:
        token = login_admin(api_url, email, password)
        password = ""
        labs = list_active_labs(api_url, token)
        if not labs:
            print("ไม่พบ Lab ที่มีสถานะ active", file=sys.stderr)
            return 1

        print("\nActive Labs:")
        for index, lab in enumerate(labs, start=1):
            print(f"{index}. {lab.get('code', '-')} — {lab.get('name', '-')}")
        selected = int(input("เลือกหมายเลข Lab: ").strip()) - 1
        if selected < 0 or selected >= len(labs):
            print("หมายเลข Lab ไม่ถูกต้อง", file=sys.stderr)
            return 1

        payload = build_device_payload_for_api(
            load_device_registration(),
            api_url,
            device_name,
        )
        registration = register_device_as_admin(
            api_url,
            token,
            int(labs[selected]["id"]),
            payload,
        )
        path = save_device_registration(registration)
    except (ValueError, EOFError):
        print("ข้อมูลที่กรอกไม่ถูกต้อง", file=sys.stderr)
        return 1
    except LabSetupError as exc:
        print(f"ลงทะเบียนไม่สำเร็จ: {exc}", file=sys.stderr)
        return 1

    print("\nลงทะเบียนสำเร็จ")
    print(f"Lab: {registration.get('lab_code')} — {registration.get('lab_name')}")
    print(f"Device ID: {registration.get('device_id')}")
    print(f"บันทึก Credential ที่: {path}")
    print("ปิดแล้วเปิด Agent ใหม่ก่อนใช้งาน")
    return 0


def main() -> int:
    args = parse_args()
    if args.cli:
        return run_cli(normalize_api_url(args.api_url), args.device_name)
    return launch_qt(normalize_api_url(args.api_url), args.device_name)


if __name__ == "__main__":
    raise SystemExit(main())
