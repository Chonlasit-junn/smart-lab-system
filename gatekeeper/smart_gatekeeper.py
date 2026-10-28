import os
import sys
import time
import threading
import queue
import winsound
import cv2
import customtkinter as ctk
from PIL import Image
from access_client import ScanClient
from camera_stream import CameraStream
from camera_preferences import load_camera_index, save_camera_index
from liveness_policy import evaluate_liveness
from liveness_runtime import load_liveness
from device_registration import DEFAULT_API_URL, load_device_registration
from registration_dialog import GatekeeperRegistrationDialog

# Keep CPU inference predictable on the 8 GB scanning machine.
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

# ── PyInstaller path fix ───────────────────────────────────────────────────────
def _base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = _base_path()

# ── CONFIG ────────────────────────────────────────────────────────────────────
CONFIG = {
    "LIVENESS_THRESHOLD": 0.72,
    "LIVENESS_SAMPLE_COUNT": 5,
    "LIVENESS_REQUIRED_PASSES": 4,
    "LIVENESS_SAMPLE_INTERVAL_SEC": 0.12,
    "LIVENESS_MIN_MOTION_SCORE": 2.0,
    "LIVENESS_CROP_SCALE": 2.7,
    "CAMERA_INDEX":       0,
    "DISPLAY_SIZE":       (600, 450),
    # Keep camera capture/detection at their existing cadence while limiting
    # expensive Tk image creation to a stable 25 FPS UI refresh.
    "DISPLAY_INTERVAL_MS": 40,
    "SPOOF_COOLDOWN_SEC": 3,
    "RESET_DELAY_MS":     3000,
    "DETECT_EVERY_N":     3,
}

API_URL = os.getenv(
    "SMART_LAB_API_URL",
    DEFAULT_API_URL,
).rstrip("/")
LAB_CODE = os.getenv("SMART_LAB_CODE", "LAB01")
DEV_MOCK_ENABLED = os.getenv("SMART_GATEKEEPER_DEV_MOCK", "0") == "1"

CLR = {
    "ready":    "#38bdf8",
    "granted":  "#10b981",
    "denied":   "#ef4444",
    "warning":  "#f59e0b",
    "panel_bg": "#1e293b",
    "dark_bg":  "#0f172a",
}

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class GatekeeperDemo(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Smart Lab — AI Gatekeeper")
        self.geometry("1024x620")
        self.resizable(False, False)

        self.lift()
        self.focus_force()
        self.attributes('-topmost', True)
        self.after(500, lambda: self.attributes('-topmost', False))

        self.is_scanning    = False
        self.models_loaded  = False
        self.in_cooldown    = False
        self._cooldown_left = 0
        self._frame_count   = 0

        self._stop_event = threading.Event()
        self._ui_events = queue.Queue()
        self._workers = []
        self._scan_client = ScanClient()
        self._camera = None
        self._camera_generation = 0
        self._camera_searching = False
        self._preview_sequence = None
        self._preview_image = None
        self._faces_at = 0.0
        self.after(40, self._drain_ui_events)
        self._detect_queue  = queue.Queue(maxsize=1)
        self._detector_lock = threading.Lock()

        self._last_faces    = []
        self.registration = load_device_registration()
        self._scanner_started = False
        self.registration_dialog_open = False
        self._registration_dialog = None

        if self.registration:
            self._start_scanner()
        else:
            self._show_registration_required()

    def _show_registration_required(self):
        self.geometry("620x350")
        frame = ctk.CTkFrame(self, corner_radius=18)
        frame.pack(fill="both", expand=True, padx=32, pady=32)
        self.registration_required_frame = frame
        ctk.CTkLabel(
            frame,
            text="ต้องลงทะเบียนกล้องก่อนใช้งาน",
            font=ctk.CTkFont(size=25, weight="bold"),
        ).pack(pady=(42, 8))
        ctk.CTkLabel(
            frame,
            text="เข้าสู่ระบบด้วยบัญชี Admin แล้วเลือก Lab ที่ติดตั้งกล้องเครื่องนี้",
            text_color="#94a3b8",
            wraplength=480,
        ).pack(pady=(0, 20))
        ctk.CTkButton(
            frame,
            text="ลงทะเบียนกล้อง",
            width=220,
            height=42,
            command=self._open_registration,
        ).pack(pady=8)

    def _start_scanner(self):
        if self._scanner_started:
            return
        self._scanner_started = True
        required_frame = getattr(self, "registration_required_frame", None)
        if required_frame is not None:
            required_frame.destroy()
        self.geometry("1024x620")
        self._current_cam_index = load_camera_index(CONFIG["CAMERA_INDEX"])
        self._remembered_camera_index = self._current_cam_index
        self._available_cameras = {self._current_cam_index: f"Camera {self._current_cam_index}"}
        self._setup_ui()
        self._init_hardware()

    def _open_registration(self):
        if self._registration_dialog is not None:
            self._registration_dialog.lift()
            return
        if self._scanner_started and self.is_scanning:
            self.sub_label.configure(text="รอให้การตรวจสอบปัจจุบันเสร็จก่อน แล้วลองอีกครั้ง")
            return
        self.registration_dialog_open = True
        self._registration_dialog = GatekeeperRegistrationDialog(
            self,
            self._on_registered,
            initial_api_url=(self.registration or {}).get("api_url", API_URL),
            on_close=self._registration_dialog_closed,
        )

    def _on_registered(self, registration):
        self.registration = registration
        self.registration_dialog_open = False
        self._registration_dialog = None
        if not self._scanner_started:
            self._start_scanner()
        else:
            self.sub_label.configure(
                text=f"ลงทะเบียนแล้ว: {registration.get('lab_code')} — {registration.get('lab_name')}"
            )

    def _registration_dialog_closed(self):
        self.registration_dialog_open = False
        self._registration_dialog = None

    # ──────────────────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────────────────

    def _start_worker(self, target, *args):
        self._workers = [worker for worker in self._workers if worker.is_alive()]
        worker = threading.Thread(target=target, args=args, daemon=True)
        self._workers.append(worker)
        worker.start()

    def _post_ui(self, callback, *args, generation=None):
        if not self._stop_event.is_set():
            self._ui_events.put((generation, callback, args))

    def _drain_ui_events(self):
        if self._stop_event.is_set():
            return
        for _ in range(32):
            try:
                generation, callback, args = self._ui_events.get_nowait()
            except queue.Empty:
                break
            if generation is None or generation == self._camera.generation:
                callback(*args)
        self.after(40, self._drain_ui_events)

    def _setup_ui(self):
        self._build_camera_panel()
        self._build_status_panel()

    def _build_camera_panel(self):
        cam = ctk.CTkFrame(self, corner_radius=15)
        cam.pack(side="left", padx=20, pady=20, fill="both", expand=True)
        self.video_label = ctk.CTkLabel(cam, text="กำลังเปิดกล้อง...")
        self.video_label.pack(expand=True, fill="both", padx=10, pady=10)

    def _build_status_panel(self):
        self.panel = ctk.CTkFrame(self, width=310, corner_radius=15, fg_color=CLR["panel_bg"])
        self.panel.pack(side="right", padx=(0, 20), pady=20, fill="y")
        self.panel.pack_propagate(False)

        ctk.CTkLabel(self.panel, text="🔐  LIVENESS CHECK", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(28, 8))

        status_box = ctk.CTkFrame(self.panel, fg_color=CLR["dark_bg"], corner_radius=12)
        status_box.pack(padx=20, pady=8, fill="x")
        self.status_label = ctk.CTkLabel(status_box, text="LOADING AI...", font=ctk.CTkFont(size=22, weight="bold"), text_color=CLR["warning"])
        self.status_label.pack(pady=22)

        self.sub_label = ctk.CTkLabel(self.panel, text="กรุณารอสักครู่...", font=ctk.CTkFont(size=13), text_color="#94a3b8")
        self.sub_label.pack(pady=(6, 2))

        self.score_badge = ctk.CTkLabel(self.panel, text="", font=ctk.CTkFont(size=12, weight="bold"), corner_radius=8)
        self.score_badge.pack(pady=4)

        self._build_score_bar()
        self._build_cooldown_box()

        ctk.CTkButton(
            self.panel,
            text="ตั้งค่าการลงทะเบียนกล้อง",
            command=self._open_registration,
            fg_color="#334155",
            hover_color="#475569",
            font=ctk.CTkFont(size=12),
        ).pack(side="bottom", padx=20, pady=(0, 8), fill="x")

        self._build_camera_selector()

        if DEV_MOCK_ENABLED:
            self._build_dev_buttons()

    def _build_camera_selector(self):
        """Dropdown สำหรับเลือกกล้อง"""
        cam_frame = ctk.CTkFrame(self.panel, fg_color="transparent")
        cam_frame.pack(padx=20, pady=(8, 0), fill="x")

        ctk.CTkLabel(
            cam_frame, text="📷  เลือกกล้อง",
            font=ctk.CTkFont(size=11), text_color="#475569",
        ).pack(anchor="w", pady=(0, 4))

        cam_labels = list(self._available_cameras.values())
        self._cam_var = ctk.StringVar(value=self._available_cameras.get(self._current_cam_index, cam_labels[0]))

        self._cam_dropdown = ctk.CTkOptionMenu(
            cam_frame,
            values=cam_labels,
            variable=self._cam_var,
            command=self._on_camera_change,
            fg_color="#0f172a",
            button_color="#334155",
            button_hover_color="#475569",
            font=ctk.CTkFont(size=12),
        )
        self._cam_dropdown.pack(fill="x")
        self._camera_search_button = ctk.CTkButton(
            cam_frame, text="ค้นหากล้องอื่น", height=26,
            command=self._refresh_cameras, fg_color="#334155", hover_color="#475569",
        )
        self._camera_search_button.pack(fill="x", pady=(6, 0))

    def _build_score_bar(self):
        bar_frame = ctk.CTkFrame(self.panel, fg_color="transparent")
        bar_frame.pack(padx=20, pady=(10, 4), fill="x")
        ctk.CTkLabel(bar_frame, text="Confidence", font=ctk.CTkFont(size=11), text_color="#475569").pack(anchor="w")
        self.score_bar = ctk.CTkProgressBar(bar_frame, height=14, corner_radius=7, progress_color=CLR["ready"])
        self.score_bar.set(0)
        self.score_bar.pack(fill="x", pady=(4, 0))
        self.score_pct_label = ctk.CTkLabel(bar_frame, text="—", font=ctk.CTkFont(size=11), text_color="#64748b")
        self.score_pct_label.pack(anchor="e")

    def _build_cooldown_box(self):
        self.cooldown_frame = ctk.CTkFrame(self.panel, fg_color="#1a0a0a", corner_radius=10)
        self.cooldown_label = ctk.CTkLabel(self.cooldown_frame, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color=CLR["denied"])
        self.cooldown_label.pack(pady=14)

    def _build_dev_buttons(self):
        dev = ctk.CTkFrame(self.panel, fg_color="transparent")
        dev.pack(side="bottom", pady=20, fill="x")
        ctk.CTkLabel(dev, text="⚡  DEV MOCK", font=ctk.CTkFont(size=11), text_color="#334155").pack(pady=(0, 6))
        ctk.CTkButton(dev, text="Force: Real Face ✓",    fg_color=CLR["granted"], hover_color="#059669", font=ctk.CTkFont(size=13, weight="bold"), command=lambda: self._force_result(True)).pack(pady=3, padx=20, fill="x")
        ctk.CTkButton(dev, text="Force: Spoof / Fake ✗", fg_color=CLR["denied"],  hover_color="#dc2626", font=ctk.CTkFont(size=13, weight="bold"), command=lambda: self._force_result(False)).pack(pady=3, padx=20, fill="x")

    # ──────────────────────────────────────────────────────────────────────
    # HARDWARE + MODEL
    # ──────────────────────────────────────────────────────────────────────

    def _on_camera_change(self, selected_label: str):
        if self.is_scanning:
            self._cam_var.set(self._available_cameras[self._current_cam_index])
            self.sub_label.configure(text="รอให้การตรวจสอบปัจจุบันเสร็จก่อนเปลี่ยนกล้อง")
            return
        new_index = next(
            (index for index, label in self._available_cameras.items() if label == selected_label),
            self._current_cam_index,
        )
        if new_index != self._current_cam_index:
            self._camera.select(new_index)
            self._sync_camera()

    def _sync_camera(self):
        searching = self._camera.discovering
        if searching != self._camera_searching:
            self._camera_searching = searching
            self._camera_search_button.configure(state="disabled" if searching else "normal")
            self._cam_dropdown.configure(state="disabled" if searching else "normal")
            if not searching and self.models_loaded and not self.in_cooldown:
                self._reset_state()
        available = self._camera.available
        if available != self._available_cameras:
            self._available_cameras = available
            if not hasattr(self, "_cam_dropdown") and len(available) > 1:
                self._build_camera_selector()
            elif hasattr(self, "_cam_dropdown"):
                self._cam_dropdown.configure(values=list(available.values()))
        self._current_cam_index = self._camera.index
        if hasattr(self, "_cam_var"):
            self._cam_var.set(available.get(self._current_cam_index, "Camera 0"))
        generation = self._camera.generation
        if generation != self._camera_generation:
            self._camera_generation = generation
            self._last_faces = []
            self._preview_sequence = None
            if self.models_loaded and not self.in_cooldown and not searching:
                self._reset_state()

    def _refresh_cameras(self):
        if self.is_scanning or self.in_cooldown:
            self.sub_label.configure(text="รอให้การตรวจสอบปัจจุบันเสร็จก่อนค้นหากล้อง")
            return
        self._camera.request_discovery()
        self._last_faces = []
        self._set_status("SEARCHING CAMERAS...", CLR["warning"], "กำลังค้นหากล้องอื่น กรุณารอสักครู่")

    def _remember_camera(self, generation):
        index = self._camera.index
        if generation != self._camera.generation:
            return
        if index != self._remembered_camera_index:
            self._remembered_camera_index = index
            try:
                save_camera_index(index)
            except OSError:
                print("[Gatekeeper] could not save camera preference")

    def _init_hardware(self):
        haar_path = os.path.join(BASE_DIR, "cv2", "data", "haarcascade_frontalface_default.xml")
        if not os.path.exists(haar_path):
            haar_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.detector = cv2.CascadeClassifier(haar_path)
        self._camera = CameraStream(self._current_cam_index, stop_event=self._stop_event)
        self._camera.start()
        self._start_worker(self._detect_loop)
        self._start_worker(self._load_models)
        self._display_loop()

    def _get_latest_frame(self):
        packet = self._camera.snapshot()
        return packet.frame if packet is not None else None

    def _detect_faces(self, frame):
        height, width = frame.shape[:2]
        small = cv2.resize(frame, (320, 240))
        scale_x = width / 320
        scale_y = height / 240
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        with self._detector_lock:
            faces = self.detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(60, 60),
            )

        return [
            (
                int(sx * scale_x),
                int(sy * scale_y),
                int(sw * scale_x),
                int(sh * scale_y),
            )
            for (sx, sy, sw, sh) in faces
        ]

    @staticmethod
    def _crop_face(frame, face, scale=2.7):
        x, y, width, height = face
        expansion = max(1.0, float(scale))
        pad_x = int(width * (expansion - 1.0) / 2.0)
        pad_y = int(height * (expansion - 1.0) / 2.0)
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(frame.shape[1], x + width + pad_x)
        y2 = min(frame.shape[0], y + height + pad_y)
        return frame[y1:y2, x1:x2]

    @staticmethod
    def _frame_motion_score(previous, current):
        if previous is None or current is None or previous.size == 0 or current.size == 0:
            return 0.0

        previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
        current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        previous_gray = cv2.resize(previous_gray, (64, 64))
        current_gray = cv2.resize(current_gray, (64, 64))
        return float(cv2.absdiff(previous_gray, current_gray).mean())

    def _detect_loop(self):
        while not self._stop_event.is_set():
            try:
                packet = self._detect_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if packet.generation != self._camera.generation or time.monotonic() - packet.captured_at > 1.0:
                continue
            faces = self._detect_faces(packet.frame)
            self._post_ui(self._accept_faces, packet, faces, generation=packet.generation)

    def _accept_faces(self, packet, faces):
        if not self.is_scanning and time.monotonic() - packet.captured_at <= 1.0:
            self._last_faces = faces
            self._faces_at = packet.captured_at

    def _load_models(self):
        try:
            self.anti_spoof, self.model_path = load_liveness(BASE_DIR)
            print("[Gatekeeper] liveness runtime loaded OK.")
            self._post_ui(self._models_ready)

        except Exception as e:
            print(f"[Gatekeeper] model load FAILED: {e}")
            err_msg = str(e)[:60]
            self._post_ui(self._set_status, "MODEL ERROR", CLR["denied"], err_msg)

    # ──────────────────────────────────────────────────────────────────────
    # DISPLAY LOOP (main thread)
    # ──────────────────────────────────────────────────────────────────────

    def _models_ready(self):
        self.models_loaded = True
        self._reset_state()

    def _display_loop(self):
        if self._stop_event.is_set():
            return
        self._sync_camera()
        packet = self._camera.snapshot()
        if packet is None or packet.sequence == self._preview_sequence:
            self.after(CONFIG["DISPLAY_INTERVAL_MS"], self._display_loop)
            return
        self._preview_sequence = packet.sequence
        self._remember_camera(packet.generation)
        # Only the preview is mutable; AI and uploads share raw pixels.
        frame = packet.frame.copy()
        h, w   = frame.shape[:2]
        cx, cy = w // 2, h // 2
        oval_a, oval_b = 110, 145

        cv2.ellipse(frame, (cx, cy), (oval_a, oval_b), 0, 0, 360, (80, 80, 80), 1)

        if (
            self.models_loaded
            and not self.is_scanning
            and not self.in_cooldown
            and not self.registration_dialog_open
            and not self._camera_searching
        ):
            self._frame_count += 1

            if self._frame_count % CONFIG["DETECT_EVERY_N"] == 0:
                try:
                    self._detect_queue.put_nowait(packet)
                except queue.Full:
                    pass

            faces = self._last_faces if time.monotonic() - self._faces_at <= 1.0 else []
            if len(faces) > 1:
                cv2.putText(frame, "กรุณาเข้าทีละคน", (w//2 - 120, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 80, 255), 2)
                self.after(0, lambda: self.sub_label.configure(text="⚠  กรุณาเข้าทีละคน"))

            elif len(faces) == 1:
                x, y, fw, fh = faces[0]
                scan_frame = packet.frame

                cv2.rectangle(frame, (x, y), (x+fw, y+fh), (255, 200, 0), 2)
                for px, py, dx, dy in [(x,y,1,1),(x+fw,y,-1,1),(x,y+fh,1,-1),(x+fw,y+fh,-1,-1)]:
                    cv2.line(frame, (px,py), (px+dx*18,py), (0,255,255), 3)
                    cv2.line(frame, (px,py), (px,py+dy*18), (0,255,255), 3)

                cv2.ellipse(frame, (cx,cy), (oval_a,oval_b), 0, 0, 360, (56,189,248), 2)

                crop = self._crop_face(scan_frame, faces[0], CONFIG["LIVENESS_CROP_SCALE"])
                if crop.size > 0:
                    self.is_scanning = True
                    self._last_faces  = []
                    self.after(0, lambda: self.status_label.configure(text="ANALYZING...", text_color=CLR["warning"]))
                    self.after(0, lambda: self.sub_label.configure(text="กำลังตรวจสอบ — กรุณาขยับศีรษะเล็กน้อย"))
                    self._start_worker(self._run_liveness, crop, scan_frame, packet.generation)

        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA))
        if self._preview_image is None:
            self._preview_image = ctk.CTkImage(light_image=image, size=CONFIG["DISPLAY_SIZE"])
            self.video_label.configure(image=self._preview_image, text="")
        else:
            self._preview_image.configure(light_image=image)

        self.after(CONFIG["DISPLAY_INTERVAL_MS"], self._display_loop)

    # ──────────────────────────────────────────────────────────────────────
    # LIVENESS
    # ──────────────────────────────────────────────────────────────────────

    def _scan_is_current(self, generation):
        return not self._stop_event.is_set() and generation == self._camera.generation

    def _run_liveness(self, crop_img, full_frame, generation):
        try:
            scores = []
            motion_scores = []
            previous_crop = crop_img
            identity_frame = full_frame

            for sample_index in range(CONFIG["LIVENESS_SAMPLE_COUNT"]):
                if not self._scan_is_current(generation):
                    return
                current_crop = crop_img if sample_index == 0 else None
                if sample_index > 0:
                    if self._stop_event.wait(CONFIG["LIVENESS_SAMPLE_INTERVAL_SEC"]):
                        return
                    current_frame = self._get_latest_frame()
                    if current_frame is None:
                        continue

                    current_faces = self._detect_faces(current_frame)
                    if len(current_faces) != 1:
                        continue

                    current_crop = self._crop_face(
                        current_frame,
                        current_faces[0],
                        CONFIG["LIVENESS_CROP_SCALE"],
                    )
                    if current_crop.size > 0:
                        identity_frame = current_frame

                if current_crop is None or current_crop.size == 0:
                    continue

                resized = cv2.resize(current_crop, (80, 80))
                score = float(self.anti_spoof.predict(resized, self.model_path)[0][1])
                scores.append(score)
                if sample_index > 0:
                    motion_scores.append(self._frame_motion_score(previous_crop, current_crop))
                previous_crop = current_crop

            decision = evaluate_liveness(
                scores,
                motion_scores,
                threshold=CONFIG["LIVENESS_THRESHOLD"],
                required_samples=CONFIG["LIVENESS_SAMPLE_COUNT"],
                required_passes=CONFIG["LIVENESS_REQUIRED_PASSES"],
                min_motion_score=CONFIG["LIVENESS_MIN_MOTION_SCORE"],
            )
            print(
                "[Gatekeeper] liveness samples="
                f"{decision.sample_count}/{CONFIG['LIVENESS_SAMPLE_COUNT']} "
                f"passes={decision.passed_samples} "
                f"motion={decision.motion_detected} reason={decision.reason}"
            )
            if not self._scan_is_current(generation):
                return
            if not decision.accepted:
                _, detail = self._identify_face(
                    None, decision.score,
                    liveness_passed=False,
                    liveness_reason=decision.reason,
                )
                self._post_ui(self._show_identity_result, False, decision.score, detail, generation=generation)
                return

            self._post_ui(
                self._set_status,
                "VERIFYING ACCESS...",
                CLR["warning"],
                "กำลังยืนยันตัวตนและตรวจสิทธิ์เข้าห้อง",
                generation=generation,
            )
            verified, detail = self._identify_face(identity_frame, decision.score)
            self._post_ui(self._show_identity_result, verified, decision.score, detail, generation=generation)
        except Exception as e:
            print(f"[Gatekeeper] liveness error: {e}")
            self._post_ui(self._reset_state, generation=generation)

    def _identify_face(self, frame, liveness_score, *, liveness_passed=True, liveness_reason=None):
        """Require an explicit, audited server authorization before granting."""
        registration = self.registration or {}
        api_url = str(registration.get("api_url") or API_URL).rstrip("/")
        return self._scan_client.verify(
            api_url, registration, frame, liveness_score,
            stop_event=self._stop_event,
            liveness_passed=liveness_passed,
            liveness_reason=liveness_reason,
            lab_code=LAB_CODE,
        )

    def _show_identity_result(self, verified: bool, score: float, detail: str):
        self.score_bar.set(score)
        self.score_pct_label.configure(text=f"{score*100:.0f}%")

        if verified:
            self._set_status(
                "ACCESS GRANTED ✓",
                CLR["granted"],
                f"อนุญาตเข้า Lab: {detail}",
            )
            self.score_badge.configure(
                text=f"  Score: {score:.2f}  ",
                fg_color="#0ea5e9",
                text_color="white",
            )
            self.score_bar.configure(progress_color=CLR["granted"])
            threading.Thread(
                target=lambda: [winsound.Beep(1000, 120), winsound.Beep(1200, 120)],
                daemon=True,
            ).start()
            self.after(CONFIG["RESET_DELAY_MS"], self._reset_state)
            return

        self._set_status("ACCESS DENIED ✗", CLR["denied"], detail)
        self.score_badge.configure(
            text=f"  Score: {score:.2f}  ",
            fg_color="#dc2626",
            text_color="white",
        )
        self.score_bar.configure(progress_color=CLR["denied"])
        threading.Thread(target=lambda: winsound.Beep(400, 600), daemon=True).start()
        self.after(CONFIG["RESET_DELAY_MS"], self._start_cooldown)

    # ──────────────────────────────────────────────────────────────────────
    # RESULT
    # ──────────────────────────────────────────────────────────────────────

    def _show_result(self, is_real: bool, score: float, detail: str = None):
        self.score_bar.set(score)
        self.score_pct_label.configure(text=f"{score*100:.0f}%")

        if is_real:
            self._set_status("DEMO: REAL FACE", CLR["granted"], "ทดสอบหน้าจอเท่านั้น — ไม่อนุญาตเข้าห้อง")
            self.score_badge.configure(text=f"  Score: {score:.2f}  ", fg_color="#0ea5e9", text_color="white")
            self.score_bar.configure(progress_color=CLR["granted"])
            threading.Thread(target=lambda: [winsound.Beep(1000,120), winsound.Beep(1200,120)], daemon=True).start()
            self.after(CONFIG["RESET_DELAY_MS"], self._reset_state)
        else:
            self._set_status("ACCESS DENIED ✗", CLR["denied"], detail or "ตรวจพบการหลอกลวง")
            self.score_badge.configure(text=f"  Score: {score:.2f}  ", fg_color="#dc2626", text_color="white")
            self.score_bar.configure(progress_color=CLR["denied"])
            threading.Thread(target=lambda: winsound.Beep(400, 600), daemon=True).start()
            self.after(CONFIG["RESET_DELAY_MS"], self._start_cooldown)

    def _set_status(self, text: str, color: str, sub: str):
        self.status_label.configure(text=text, text_color=color)
        self.sub_label.configure(text=sub)

    # ──────────────────────────────────────────────────────────────────────
    # COOLDOWN
    # ──────────────────────────────────────────────────────────────────────

    def _start_cooldown(self):
        self.in_cooldown    = True
        self._cooldown_left = CONFIG["SPOOF_COOLDOWN_SEC"]
        self.score_badge.configure(text="", fg_color="transparent")
        self.cooldown_frame.pack(padx=20, pady=8, fill="x")
        self._tick_cooldown()

    def _tick_cooldown(self):
        if self._cooldown_left > 0:
            self.cooldown_label.configure(text=f"🚫  ระบบล็อกชั่วคราว  {self._cooldown_left} วินาที")
            self._cooldown_left -= 1
            self.after(1000, self._tick_cooldown)
        else:
            self.cooldown_frame.pack_forget()
            self.in_cooldown = False
            self._reset_state()

    # ──────────────────────────────────────────────────────────────────────
    # RESET / DEV / CLEANUP
    # ──────────────────────────────────────────────────────────────────────

    def _reset_state(self):
        self._set_status("READY TO SCAN", CLR["ready"], "หันหน้าเข้าหากล้อง")
        self.score_badge.configure(text="", fg_color="transparent")
        self.score_bar.set(0)
        self.score_bar.configure(progress_color=CLR["ready"])
        self.score_pct_label.configure(text="—")
        self.is_scanning  = False
        self._last_faces  = []

    def _force_result(self, is_real: bool):
        if not DEV_MOCK_ENABLED or self.is_scanning or not self.models_loaded or self.in_cooldown:
            return
        self.is_scanning = True
        self._set_status("VERIFYING...", CLR["warning"], "")
        self.after(800, self._show_result, is_real, 0.95 if is_real else 0.18)

    def on_closing(self):
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        if self._camera is not None:
            self._camera.stop()
        # Native reads finish in their owner threads; late grants are discarded.
        self._start_worker(self._scan_client.close)
        self._close_deadline = time.monotonic() + 1.0
        self._finish_closing()

    def _finish_closing(self):
        alive = any(worker.is_alive() for worker in self._workers)
        alive = alive or (self._camera is not None and self._camera.is_alive())
        if alive and time.monotonic() < self._close_deadline:
            self.after(40, self._finish_closing)
        else:
            self.destroy()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--liveness-self-test":
        import json
        from pathlib import Path
        import numpy as np

        try:
            predictor, model_path = load_liveness(BASE_DIR, "onnx")
            probabilities = predictor.predict(np.zeros((80, 80, 3), dtype=np.uint8), model_path)
            report = {"ok": True, "backend": "onnx", "precision": "FP32",
                      "probabilities": probabilities.tolist(), "torch_loaded": "torch" in sys.modules}
        except Exception as exc:
            report = {"ok": False, "error_type": type(exc).__name__}
        Path(sys.argv[2]).write_text(json.dumps(report, indent=2), encoding="utf-8")
        raise SystemExit(0 if report["ok"] else 1)
    app = GatekeeperDemo()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
