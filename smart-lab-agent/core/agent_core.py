import os
import psutil
import ctypes
import json
from datetime import datetime
import pygetwindow as gw
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from .logger import logger
from .config import API_URL, DEBUG_MODE, IGNORE_SYSTEM_APPS, DEVICE_NAME, DEVICE_MAC
from .network import NetworkWorker, post_with_retry
from .store import PendingLogStore
import requests

class SmartLabAgent(QObject):
    violation_detected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.usage_segments = []
        self.current_activity_name = None
        self.current_activity_started_at = None
        self.current_session_id = None
        self.info_bar       = None
        self.overlay        = None
        self.forbidden_words = []   # โหลดจาก /admin/blacklist ตอน start_monitoring
        self.violation_reported = False
        self.monitor_timer  = QTimer()
        self.monitor_timer.timeout.connect(self.track_usage)
        self._log_store     = PendingLogStore()
        self._flush_pending_logs()  # ส่ง logs ค้างจาก session ก่อนหน้า (ถ้ามี)

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
        self.forbidden_words = [
            "bittorrent", "cheatengine",
            "genshin", "genshinimpact",
            "star rail", "starrail",       # window title และ process name
        ]

    def start_monitoring(self, session_id):
        self.current_session_id = session_id
        self.usage_segments = []
        self.current_activity_name = None
        self.current_activity_started_at = None
        self.violation_reported = False
        self.fetch_blacklist()
        self.monitor_timer.start(5000)

    def _close_current_activity(self, ended_at=None):
        if not self.current_activity_name or not self.current_activity_started_at:
            return

        ended_at = ended_at or datetime.now()
        duration = max(
            0,
            int((ended_at - self.current_activity_started_at).total_seconds()),
        )
        if duration > 0:
            self.usage_segments.append({
                "name": self.current_activity_name,
                "started_at": self.current_activity_started_at.isoformat(timespec="seconds"),
                "ended_at": ended_at.isoformat(timespec="seconds"),
                "duration": duration,
            })
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

    def report_violation(self, program_name, reason):
        if self.violation_reported or not self.current_session_id:
            return

        self.violation_reported = True
        try:
            response = post_with_retry(
                f"{API_URL}/agent/log-violation",
                data={
                    "session_id": self.current_session_id,
                    "program_name": program_name,
                    "reason": reason,
                    "action_taken": "logout",
                },
            )
            print(f"Violation response: {response.status_code if response else 'Timeout'}")
        except Exception as e:
            print(f"บันทึก violation ไม่ได้: {e}")

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
                            reason = f"ไม่อนุญาตให้เปิดแอป: {word.title()}"
                            self.report_violation(p_name, reason)
                            if self.info_bar:
                                self.info_bar.trigger_logout(reason=reason)
                            return
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

            # ── ด่านที่ 2: ตรวจจาก Active Window title ──────────────────────
            active_win = gw.getActiveWindow()
            if not active_win or not active_win.title:
                self._close_current_activity(datetime.now())
                return

            raw_title  = active_win.title.strip()
            title_lower = raw_title.lower()

            for word in self.forbidden_words:
                if not word:
                    continue
                # FIX 4: compare ตรงๆ เช่น "star rail" in "star rail - loading" → True
                if word in title_lower:
                    reason = f"ไม่อนุญาตให้เปิดใช้งาน: {word.title()}"
                    self.report_violation(raw_title, reason)
                    if self.info_bar:
                        self.info_bar.trigger_logout(reason=reason)
                    return

            # ── บันทึกสถิติการใช้งานปกติ ────────────────────────────────────
            # ใช้ process name จาก psutil แทนการ parse window title
            app_name = self._get_process_name_from_window(active_win)

            self._track_active_activity(app_name, datetime.now())

        except Exception as e:
            logger.error(f"track_usage error: {e}", exc_info=True)

    def stop_and_send_logs(self, session_id):
        self.monitor_timer.stop()
        self._close_current_activity(datetime.now())

        summary = self.usage_segments
        if not summary:
            logger.info("ไม่มีสถิติการใช้งานที่บันทึกได้")

            try:
                end_response = post_with_retry(
                    f"{API_URL}/agent/end-session",
                    data={"session_id": session_id},
                )
                logger.info(f"End session response: {end_response.status_code if end_response else 'Timeout'}")
            except Exception as e:
                logger.error(f"ปิด Session ไม่ได้: {e}")

            self.current_session_id = None
            self._after_send_logs()
            return

        # เก็บลง local DB ก่อน — แม้ network ล้มเหลวข้อมูลไม่หาย
        try:
            row_id = self._log_store.save(
                session_id, summary,
                hostname=DEVICE_NAME, mac_address=DEVICE_MAC,
            )
        except Exception as e:
            logger.error(f"Save to local DB failed: {e}", exc_info=True)
            row_id = None

        logger.info(f"ส่งข้อมูลไป Backend — Data: {summary}")

        self._send_worker = NetworkWorker(
            self._do_send_logs, session_id, summary, DEVICE_NAME, DEVICE_MAC
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
                "device": DEVICE_NAME,
                "mac": DEVICE_MAC,
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
                hostname or DEVICE_NAME, mac or DEVICE_MAC
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
