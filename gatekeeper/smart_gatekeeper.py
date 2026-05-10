"""
Smart Lab Gatekeeper — Liveness Demo

Mockup สำหรับโชว์ระบบ:
  1. ตรวจจับใบหน้าจากกล้อง (OpenCV Haar Cascade)
  2. ตรวจ Liveness ด้วย Silent-Face-Anti-Spoofing
  3. แสดงผล REAL / SPOOF — ยังไม่ตรวจสอบตัวตน ไม่มี API call
"""

import os
import sys
import threading
import cv2
import numpy as np
import customtkinter as ctk
from PIL import Image

# ==========================================
# CONFIGURATION
# ==========================================
CONFIG = {
    "LIVENESS_THRESHOLD": 0.72,   # score เกินนี้ = คนจริง
    "CAMERA_INDEX": 0,
    "DISPLAY_SIZE": (600, 450),
}

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class GatekeeperDemo(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Smart Lab — Liveness Demo")
        self.geometry("1024x600")
        self.resizable(False, False)

        # ── state ──────────────────────────────────────────────────────────
        self.is_scanning   = False   # ป้องกัน thread ซ้อนกัน
        self.models_loaded = False

        self._setup_ui()
        self._init_hardware()

    # ──────────────────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        # ---- left: camera feed ----
        cam_frame = ctk.CTkFrame(self, corner_radius=15)
        cam_frame.pack(side="left", padx=20, pady=20, fill="both", expand=True)

        self.video_label = ctk.CTkLabel(cam_frame, text="กำลังเปิดกล้อง...")
        self.video_label.pack(expand=True, fill="both", padx=10, pady=10)

        # ---- right: status panel ----
        self.panel = ctk.CTkFrame(self, width=300, corner_radius=15, fg_color="#1e293b")
        self.panel.pack(side="right", padx=(0, 20), pady=20, fill="y")
        self.panel.pack_propagate(False)

        ctk.CTkLabel(
            self.panel, text="LIVENESS CHECK",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(30, 10))

        # status box (LOADING / READY / ANALYZING / result)
        status_box = ctk.CTkFrame(self.panel, fg_color="#0f172a", corner_radius=10)
        status_box.pack(padx=20, pady=10, fill="x")

        self.status_label = ctk.CTkLabel(
            status_box, text="LOADING AI...",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#f59e0b",
        )
        self.status_label.pack(pady=20)

        # sub-text below status (score, hint)
        self.sub_label = ctk.CTkLabel(
            self.panel, text="กรุณารอสักครู่...",
            font=ctk.CTkFont(size=14),
        )
        self.sub_label.pack(pady=16)

        # score badge (แสดงหลัง scan)
        self.score_badge = ctk.CTkLabel(
            self.panel, text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
        )
        self.score_badge.pack(pady=4)

        # ---- dev buttons ----
        dev_frame = ctk.CTkFrame(self.panel, fg_color="transparent")
        dev_frame.pack(side="bottom", pady=24, fill="x")

        ctk.CTkLabel(
            dev_frame, text="⚡ DEV MOCK",
            font=ctk.CTkFont(size=11), text_color="#64748b",
        ).pack(pady=(0, 6))

        ctk.CTkButton(
            dev_frame, text="Force: Real Face",
            fg_color="#10b981", hover_color="#059669",
            command=lambda: self._force_result(True),
        ).pack(pady=4, padx=20, fill="x")

        ctk.CTkButton(
            dev_frame, text="Force: Spoof / Fake",
            fg_color="#ef4444", hover_color="#dc2626",
            command=lambda: self._force_result(False),
        ).pack(pady=4, padx=20, fill="x")

    # ──────────────────────────────────────────────────────────────────────
    # HARDWARE + MODEL INIT
    # ──────────────────────────────────────────────────────────────────────

    def _init_hardware(self):
        self.cap = cv2.VideoCapture(CONFIG["CAMERA_INDEX"])
        # haar cascade สำหรับ detect หน้าเบื้องต้นก่อนส่งให้ anti-spoof
        self.detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        # load model ใน background เพื่อไม่ block UI
        threading.Thread(target=self._load_models, daemon=True).start()
        self._update_camera()

    def _load_models(self):
        """โหลด Silent-Face-Anti-Spoofing model ใน background thread"""
        try:
            repo_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "Silent-Face-Anti-Spoofing"
            )
            sys.path.append(repo_path)

            self.model_path = os.path.join(
                repo_path, "resources", "anti_spoof_models",
                "2.7_80x80_MiniFASNetV2.pth"
            )

            from src.anti_spoof_predict import AntiSpoofPredict

            # anti-spoof library ต้องรันจาก repo directory
            orig_cwd = os.getcwd()
            os.chdir(repo_path)
            self.anti_spoof = AntiSpoofPredict(device_id=None)
            os.chdir(orig_cwd)

            print("[Gatekeeper] Anti-spoof model loaded.")
            self.models_loaded = True
            self.after(0, self._reset_state)

        except Exception as e:
            print(f"[Gatekeeper] Model load failed: {e}")
            self.after(0, lambda: self.status_label.configure(
                text="MODEL ERROR", text_color="#ef4444"
            ))

    # ──────────────────────────────────────────────────────────────────────
    # CAMERA LOOP
    # ──────────────────────────────────────────────────────────────────────

    def _update_camera(self):
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)

            if self.models_loaded and not self.is_scanning:
                gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.detector.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=4, minSize=(100, 100)
                )

                if len(faces) > 0:
                    # เลือกหน้าที่ใหญ่ที่สุด (คนที่อยู่ใกล้สุด)
                    x, y, w, h = max(faces, key=lambda r: r[2] * r[3])

                    # padding รอบหน้าเล็กน้อยก่อนส่งให้ model
                    pad = 15
                    x1 = max(0, x - pad)
                    y1 = max(0, y - pad)
                    x2 = min(frame.shape[1], x + w + pad)
                    y2 = min(frame.shape[0], y + h + pad)

                    # วาดกรอบหน้า
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 200, 0), 2)
                    # corner marks
                    for px, py, dx, dy in [(x,y,1,1),(x+w,y,-1,1),(x,y+h,1,-1),(x+w,y+h,-1,-1)]:
                        L = 18
                        cv2.line(frame, (px, py), (px + dx*L, py), (0, 255, 255), 3)
                        cv2.line(frame, (px, py), (px, py + dy*L), (0, 255, 255), 3)

                    crop = frame[y1:y2, x1:x2]
                    if crop.size > 0:
                        self.is_scanning = True
                        self.after(0, lambda: self.status_label.configure(
                            text="ANALYZING...", text_color="#f59e0b"
                        ))
                        self.after(0, lambda: self.sub_label.configure(text="กำลังตรวจสอบ..."))
                        threading.Thread(
                            target=self._run_liveness,
                            args=(crop.copy(),),
                            daemon=True,
                        ).start()

            # แปลง frame เพื่อแสดงบน CTk
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            img   = Image.fromarray(rgb)
            imgtk = ctk.CTkImage(
                light_image=img, dark_image=img,
                size=CONFIG["DISPLAY_SIZE"],
            )
            self.video_label.configure(image=imgtk, text="")
            self.video_label.image = imgtk

        self.after(15, self._update_camera)

    # ──────────────────────────────────────────────────────────────────────
    # LIVENESS CHECK
    # ──────────────────────────────────────────────────────────────────────

    def _run_liveness(self, crop_img):
        """รัน anti-spoof model แล้วเอาผลมาอัปเดต UI ผ่าน after()"""
        try:
            resized = cv2.resize(crop_img, (80, 80))
            # prediction คืน array shape (1, 3) → index 1 = real score
            score   = float(self.anti_spoof.predict(resized, self.model_path)[0][1])
            is_real = score > CONFIG["LIVENESS_THRESHOLD"]

            self.after(0, self._show_result, is_real, score)

        except Exception as e:
            print(f"[Gatekeeper] liveness error: {e}")
            self.after(0, self._reset_state)

    # ──────────────────────────────────────────────────────────────────────
    # RESULT DISPLAY
    # ──────────────────────────────────────────────────────────────────────

    def _show_result(self, is_real: bool, score: float):
        if is_real:
            self.status_label.configure(text="REAL FACE ✓",  text_color="#10b981")
            self.sub_label.configure(text="ตรวจพบใบหน้าจริง")
            self.score_badge.configure(
                text=f"  Score: {score:.2f}  ",
                fg_color="#0ea5e9", text_color="white",
            )
        else:
            self.status_label.configure(text="SPOOF DETECTED", text_color="#ef4444")
            self.sub_label.configure(text="ตรวจพบการหลอกลวง (ภาพถ่าย/หน้าจอ)")
            self.score_badge.configure(
                text=f"  Score: {score:.2f}  ",
                fg_color="#dc2626", text_color="white",
            )

        # รีเซ็ตหลัง 3 วินาที
        self.after(3000, self._reset_state)

    def _reset_state(self):
        self.status_label.configure(text="READY TO SCAN", text_color="#38bdf8")
        self.sub_label.configure(text="หันหน้าเข้าหากล้อง")
        self.score_badge.configure(text="", fg_color="transparent")
        self.is_scanning = False

    # ──────────────────────────────────────────────────────────────────────
    # DEV MOCK
    # ──────────────────────────────────────────────────────────────────────

    def _force_result(self, is_real: bool):
        """bypass AI สำหรับ demo — กด Force button แล้วได้ผลทันที"""
        if self.is_scanning or not self.models_loaded:
            return
        self.is_scanning = True
        self.status_label.configure(text="VERIFYING...", text_color="#f59e0b")
        mock_score = 0.95 if is_real else 0.12
        self.after(800, self._show_result, is_real, mock_score)

    # ──────────────────────────────────────────────────────────────────────
    # CLEANUP
    # ──────────────────────────────────────────────────────────────────────

    def on_closing(self):
        self.cap.release()
        self.destroy()


if __name__ == "__main__":
    app = GatekeeperDemo()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()