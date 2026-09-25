"""Small Admin-authenticated setup window for registering a Gatekeeper."""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

import customtkinter as ctk

from device_registration import (
    DEFAULT_API_URL,
    RegistrationError,
    build_device_payload,
    list_active_labs,
    load_device_registration,
    login_admin,
    register_gatekeeper_as_admin,
    save_device_registration,
)


class GatekeeperRegistrationDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: Any,
        on_registered: Callable[[dict[str, Any]], None],
        *,
        initial_api_url: str = DEFAULT_API_URL,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.parent = parent
        self.on_registered = on_registered
        self.on_close = on_close
        saved = load_device_registration() or {}
        self.admin_token: Optional[str] = None
        self.labs: list[dict[str, Any]] = []
        self._busy = False
        self._closed = False

        self.title("Smart Lab — Register Gatekeeper")
        self.geometry("560x570")
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)

        frame = ctk.CTkFrame(self, corner_radius=16)
        frame.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(
            frame,
            text="ลงทะเบียนกล้อง Gatekeeper",
            font=ctk.CTkFont(size=23, weight="bold"),
        ).pack(anchor="w", padx=22, pady=(22, 4))
        ctk.CTkLabel(
            frame,
            text="ใช้บัญชี Admin เพื่อเลือก Lab และผูกสิทธิ์กับกล้องเครื่องนี้",
            text_color="#94a3b8",
            wraplength=490,
            justify="left",
        ).pack(anchor="w", padx=22, pady=(0, 15))

        self.api_url = self._field(frame, "Backend URL", initial_api_url or DEFAULT_API_URL)
        self.email = self._field(frame, "Admin Email", "")
        self.password = self._field(frame, "Admin Password", "", show="*")
        self.device_name = self._field(
            frame,
            "ชื่อกล้อง/เครื่อง",
            str(saved.get("device_name") or "").strip() or None,
        )

        ctk.CTkLabel(frame, text="Lab ที่ติดตั้ง", anchor="w").pack(fill="x", padx=22, pady=(8, 2))
        self.lab_choice = ctk.StringVar(value="โหลดรายชื่อ Lab ก่อน")
        self.lab_menu = ctk.CTkOptionMenu(
            frame,
            variable=self.lab_choice,
            values=["โหลดรายชื่อ Lab ก่อน"],
            state="disabled",
            height=38,
        )
        self.lab_menu.pack(fill="x", padx=22, pady=(0, 12))

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", padx=22, pady=(4, 8))
        self.load_button = ctk.CTkButton(
            buttons,
            text="โหลดรายชื่อ Lab",
            command=self.load_labs,
            fg_color="#334155",
            hover_color="#475569",
        )
        self.load_button.pack(side="left")
        self.register_button = ctk.CTkButton(
            buttons,
            text="ลงทะเบียนกล้อง",
            command=self.register_device,
            state="disabled",
        )
        self.register_button.pack(side="right")

        self.status = ctk.CTkLabel(
            frame,
            text="รหัสผ่าน Admin และ access token จะไม่ถูกบันทึกลงเครื่อง",
            text_color="#94a3b8",
            wraplength=490,
            justify="left",
        )
        self.status.pack(anchor="w", padx=22, pady=(8, 18))
        self.grab_set()

    def _field(self, parent: Any, label: str, value: Optional[str], show: Optional[str] = None):
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x", padx=22, pady=(7, 2))
        entry = ctk.CTkEntry(parent, height=38, show=show or "")
        entry.pack(fill="x", padx=22)
        if value:
            entry.insert(0, value)
        return entry

    def _set_busy(self, busy: bool, status: str) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.api_url.configure(state=state)
        self.email.configure(state=state)
        self.password.configure(state=state)
        self.device_name.configure(state=state)
        self.load_button.configure(state=state)
        self.register_button.configure(
            state="disabled" if busy or not self.admin_token or not self.labs else "normal"
        )
        self.status.configure(text=status, text_color="#f59e0b" if busy else "#94a3b8")

    def _run_async(self, operation: Callable[[], Any], on_success: Callable[[Any], None]) -> None:
        self._set_busy(True, "กำลังติดต่อ Backend...")

        def worker() -> None:
            try:
                result = operation()
            except (RegistrationError, ValueError) as exc:
                self._post(self._operation_failed, str(exc))
                return
            except Exception:
                self._post(self._operation_failed, "เกิดข้อผิดพลาดระหว่างติดต่อ Backend")
                return
            self._post(self._operation_succeeded, on_success, result)

        threading.Thread(target=worker, daemon=True).start()

    def _post(self, callback: Callable[..., None], *args: Any) -> None:
        if self._closed:
            return
        try:
            self.after(0, callback, *args)
        except Exception:
            # The dialog may have closed while its request was in flight.
            pass

    def _operation_failed(self, message: str) -> None:
        self._set_busy(False, f"ไม่สำเร็จ: {message}")
        self.status.configure(text_color="#f87171")

    def _operation_succeeded(self, callback: Callable[[Any], None], result: Any) -> None:
        self._set_busy(False, "พร้อมดำเนินการ")
        callback(result)

    def load_labs(self) -> None:
        api_url = self.api_url.get().strip()
        email = self.email.get().strip()
        password = self.password.get()
        if not api_url or not email or not password:
            self._operation_failed("กรุณากรอก Backend URL, Admin Email และรหัสผ่าน")
            return

        self.admin_token = None
        self.labs = []
        self.lab_menu.configure(values=["กำลังโหลด..."])
        self.lab_choice.set("กำลังโหลด...")
        self.lab_menu.configure(state="disabled")

        def operation() -> tuple[str, list[dict[str, Any]]]:
            token = login_admin(api_url, email, password)
            return token, list_active_labs(api_url, token)

        def completed(result: tuple[str, list[dict[str, Any]]]) -> None:
            self.admin_token, self.labs = result
            self.password.delete(0, "end")
            labels = [
                f"{lab.get('code', '-')} — {lab.get('name', 'ไม่ระบุชื่อ Lab')}"
                for lab in self.labs
            ]
            if not labels:
                self.lab_menu.configure(values=["ไม่พบ Lab ที่ active"], state="disabled")
                self.lab_choice.set("ไม่พบ Lab ที่ active")
                self._set_busy(False, "ไม่พบ Lab ที่เปิดใช้งาน")
                return
            self.lab_menu.configure(values=labels, state="normal")
            self.lab_choice.set(labels[0])
            self.register_button.configure(state="normal")
            self._set_busy(False, f"พบ {len(labels)} Lab ที่เปิดใช้งาน เลือก Lab แล้วลงทะเบียนได้")

        self._run_async(operation, completed)

    def register_device(self) -> None:
        if not self.admin_token or not self.labs:
            self._operation_failed("กรุณาโหลดรายชื่อ Lab ก่อน")
            return

        selected_label = self.lab_choice.get()
        labels = [
            f"{lab.get('code', '-')} — {lab.get('name', 'ไม่ระบุชื่อ Lab')}"
            for lab in self.labs
        ]
        if selected_label not in labels:
            self._operation_failed("กรุณาเลือก Lab")
            return

        lab = self.labs[labels.index(selected_label)]
        api_url = self.api_url.get().strip()
        access_token = self.admin_token
        device_name = self.device_name.get().strip()

        def operation() -> tuple[dict[str, Any], Any]:
            payload = build_device_payload(load_device_registration(), api_url, device_name)
            registration = register_gatekeeper_as_admin(
                api_url,
                access_token,
                int(lab["id"]),
                payload,
            )
            path = save_device_registration(registration)
            return registration, path

        def completed(result: tuple[dict[str, Any], Any]) -> None:
            registration, path = result
            self.admin_token = None
            self.password.delete(0, "end")
            self.status.configure(
                text=f"ลงทะเบียนสำเร็จ: {registration.get('lab_code')} — บันทึก credential ไว้ที่ {path}",
                text_color="#34d399",
            )
            self.on_registered(registration)
            self.destroy()

        self._run_async(operation, completed)

    def _close(self) -> None:
        self._closed = True
        self.admin_token = None
        if self.on_close:
            self.on_close()
        self.destroy()
