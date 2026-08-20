import json
import os
import queue
import sys
import threading
import traceback
import winsound
import cv2
import customtkinter as ctk
from facenet_pytorch import InceptionResnetV1
import numpy as np
from PIL import Image
from supabase import Client, create_client
import torch


# ── PyInstaller path fix ───────────────────────────────────────────────────────
def _base_path():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_path()

# ── CONFIG ────────────────────────────────────────────────────────────────────
CONFIG = {
    "LIVENESS_THRESHOLD": 0.72,
    "SIMILARITY_THRESHOLD": 0.65,  # ค่า Cosine Similarity (ยิ่งใกล้ 1.0 ยิ่งเหมือนกัน)
    "CAMERA_INDEX": 0,
    "DISPLAY_SIZE": (600, 450),
    "SPOOF_COOLDOWN_SEC": 3,
    "RESET_DELAY_MS": 3000,
    "DETECT_EVERY_N": 3,
    # ── ข้อมูลเชื่อมต่อ SUPABASE ──
    "SUPABASE_URL": "https://lilvtjyupffpilyossfv.supabase.co",
    "SUPABASE_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxpbHZ0anl1cGZmcGlseW9zc2Z2Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTU1NDEyMSwiZXhwIjoyMDkxMTMwMTIxfQ.2neE01VHuDeI5anjIuqpfSwh2KVW95RWYs-MgpF3kuQ",
    "SUPABASE_TABLE": "users",  # ชื่อ Table ในฐานข้อมูล
}

CLR = {
    "ready": "#38bdf8",
    "granted": "#10b981",
    "denied": "#ef4444",
    "warning": "#f59e0b",
    "panel_bg": "#1e293b",
    "dark_bg": "#0f172a",
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
        self.attributes("-topmost", True)
        self.after(500, lambda: self.attributes("-topmost", False))

        self.is_scanning = False
        self.models_loaded = False
        self.in_cooldown = False
        self._cooldown_left = 0
        self._frame_count = 0

        self.known_face_embeddings = []
        self.known_face_names = []

        self._frame_queue = queue.Queue(maxsize=1)
        self._detect_queue = queue.Queue(maxsize=1)

        self._last_faces = []
        self._last_frame_hw = (480, 640)

        self._setup_ui()
        self._init_hardware()

    # ──────────────────────────────────────────────────────────────────────
    # UI SETUP
    # ──────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self._build_camera_panel()
        self._build_status_panel()

    def _build_camera_panel(self):
        cam = ctk.CTkFrame(self, corner_radius=15)
        cam.pack(side="left", padx=20, pady=20, fill="both", expand=True)
        self.video_label = ctk.CTkLabel(cam, text="กำลังเปิดกล้อง...")
        self.video_label.pack(expand=True, fill="both", padx=10, pady=10)

    def _build_status_panel(self):
        self.panel = ctk.CTkFrame(
            self, width=310, corner_radius=15, fg_color=CLR["panel_bg"]
        )
        self.panel.pack(side="right", padx=(0, 20), pady=20, fill="y")
        self.panel.pack_propagate(False)

        ctk.CTkLabel(
            self.panel,
            text="🔐  SMART GATEKEEPER",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(28, 8))

        status_box = ctk.CTkFrame(
            self.panel, fg_color=CLR["dark_bg"], corner_radius=12
        )
        status_box.pack(padx=20, pady=8, fill="x")
        self.status_label = ctk.CTkLabel(
            status_box,
            text="CONNECTING...",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=CLR["warning"],
        )
        self.status_label.pack(pady=22)

        self.sub_label = ctk.CTkLabel(
            self.panel,
            text="กำลังดาวน์โหลดข้อมูลใบหน้า...",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8",
        )
        self.sub_label.pack(pady=(6, 2))

        self.score_badge = ctk.CTkLabel(
            self.panel,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
        )
        self.score_badge.pack(pady=4)

        self._build_score_bar()
        self._build_cooldown_box()
        self._build_dev_buttons()

    def _build_score_bar(self):
        bar_frame = ctk.CTkFrame(self.panel, fg_color="transparent")
        bar_frame.pack(padx=20, pady=(10, 4), fill="x")
        ctk.CTkLabel(
            bar_frame,
            text="Liveness Confidence",
            font=ctk.CTkFont(size=11),
            text_color="#475569",
        ).pack(anchor="w")
        self.score_bar = ctk.CTkProgressBar(
            bar_frame,
            height=14,
            corner_radius=7,
            progress_color=CLR["ready"],
        )
        self.score_bar.set(0)
        self.score_bar.pack(fill="x", pady=(4, 0))
        self.score_pct_label = ctk.CTkLabel(
            bar_frame,
            text="—",
            font=ctk.CTkFont(size=11),
            text_color="#64748b",
        )
        self.score_pct_label.pack(anchor="e")

    def _build_cooldown_box(self):
        self.cooldown_frame = ctk.CTkFrame(
            self.panel, fg_color="#1a0a0a", corner_radius=10
        )
        self.cooldown_label = ctk.CTkLabel(
            self.cooldown_frame,
            text="",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=CLR["denied"],
        )
        self.cooldown_label.pack(pady=14)

    def _build_dev_buttons(self):
        dev = ctk.CTkFrame(self.panel, fg_color="transparent")
        dev.pack(side="bottom", pady=20, fill="x")
        ctk.CTkLabel(
            dev,
            text="⚡  MANAGEMENT",
            font=ctk.CTkFont(size=11),
            text_color="#334155",
        ).pack(pady=(0, 6))
        ctk.CTkButton(
            dev,
            text="Sync Supabase DB",
            fg_color="#334155",
            hover_color="#475569",
            font=ctk.CTkFont(size=12),
            command=lambda: threading.Thread(
                target=self._load_supabase_embeddings, daemon=True
            ).start(),
        ).pack(pady=3, padx=20, fill="x")

    # ──────────────────────────────────────────────────────────────────────
    # HARDWARE & MODEL & SUPABASE
    # ──────────────────────────────────────────────────────────────────────

    def _init_hardware(self):
        self.cap = cv2.VideoCapture(CONFIG["CAMERA_INDEX"])
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        haar_path = os.path.join(
            BASE_DIR, "cv2", "data", "haarcascade_frontalface_default.xml"
        )
        if not os.path.exists(haar_path):
            haar_path = (
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
        self.detector = cv2.CascadeClassifier(haar_path)

        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._detect_loop, daemon=True).start()
        threading.Thread(target=self._load_all_resources, daemon=True).start()

        self._display_loop()

    def _load_all_resources(self):
        self._load_supabase_embeddings()
        self._load_models()

    def _load_supabase_embeddings(self):
        try:
            print("[Supabase] Fetching face embeddings...")
            supabase: Client = create_client(
                CONFIG["SUPABASE_URL"], CONFIG["SUPABASE_KEY"]
            )
            response = (
                supabase.table(CONFIG["SUPABASE_TABLE"])
                .select("first_name, face_embedding")
                .execute()
            )

            encodings, names = [], []
            for row in response.data:
                emb = row.get("face_embedding")
                if emb:
                    if isinstance(emb, str):
                        emb = json.loads(emb)
                    # L2 Normalization สำหรับ Cosine Similarity
                    vec = np.array(emb, dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    if norm > 0:
                        vec = vec / norm
                    encodings.append(vec)
                    names.append(row.get("first_name", "Unknown"))

            self.known_face_embeddings = encodings
            self.known_face_names = names
            print(
                f"[Supabase] Loaded {len(self.known_face_embeddings)} authorized users."
            )
        except Exception as e:
            print(f"[Supabase] Error loading embeddings: {e}")
            traceback.print_exc()

    def _capture_loop(self):
        while True:
            ret, frame = self.cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
                self._frame_queue.put_nowait(frame)

    def _detect_loop(self):
        while True:
            frame = self._detect_queue.get()
            h, w = frame.shape[:2]

            small = cv2.resize(frame, (320, 240))
            scale_x = w / 320
            scale_y = h / 240
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = self.detector.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60)
            )

            scaled = []
            for sx, sy, sw, sh in faces:
                scaled.append(
                    (
                        int(sx * scale_x),
                        int(sy * scale_y),
                        int(sw * scale_x),
                        int(sh * scale_y),
                    )
                )

            self._last_faces = scaled
            self._last_frame_hw = (h, w)

    def _load_models(self):
        orig = os.getcwd()
        try:
            # 1. โหลด FaceNet
            print("[FaceNet] Loading FaceNet InceptionResnetV1...")
            self.facenet = InceptionResnetV1(pretrained="vggface2").eval()

            # 2. โหลด Silent-Face-Anti-Spoofing
            repo_path = os.path.join(
                BASE_DIR, "gatekeeper", "Silent-Face-Anti-Spoofing"
            )
            if not os.path.exists(repo_path):
                repo_path = os.path.join(BASE_DIR, "Silent-Face-Anti-Spoofing")

            model_file = os.path.join(
                repo_path,
                "resources",
                "anti_spoof_models",
                "2.7_80x80_MiniFASNetV2.pth",
            )

            if not os.path.exists(repo_path) or not os.path.exists(model_file):
                raise FileNotFoundError(
                    f"Model or Directory not found: {model_file}"
                )

            if repo_path not in sys.path:
                sys.path.insert(0, repo_path)

            self.model_path = model_file
            from src.anti_spoof_predict import AntiSpoofPredict

            try:
                os.chdir(repo_path)
                self.anti_spoof = AntiSpoofPredict(device_id=0)
            finally:
                os.chdir(orig)

            print("[Gatekeeper] All AI Models loaded successfully.")
            self.models_loaded = True
            self.after(0, self._reset_state)

        except Exception as e:
            print(f"[Gatekeeper] Model load FAILED: {e}")
            err_msg = str(e)[:60]
            self.after(
                0,
                lambda msg=err_msg: self._set_status(
                    "MODEL ERROR", CLR["denied"], msg
                ),
            )

    # ──────────────────────────────────────────────────────────────────────
    # DISPLAY LOOP
    # ──────────────────────────────────────────────────────────────────────

    def _display_loop(self):
        try:
            frame = self._frame_queue.get_nowait()
        except queue.Empty:
            self.after(30, self._display_loop)
            return

        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        oval_a, oval_b = 110, 145

        cv2.ellipse(
            frame, (cx, cy), (oval_a, oval_b), 0, 0, 360, (80, 80, 80), 1
        )

        if self.models_loaded and not self.is_scanning and not self.in_cooldown:
            self._frame_count += 1

            if self._frame_count % CONFIG["DETECT_EVERY_N"] == 0:
                try:
                    self._detect_queue.put_nowait(frame.copy())
                except queue.Full:
                    pass

            faces = self._last_faces
            if len(faces) > 1:
                cv2.putText(
                    frame,
                    "กรุณาเข้าทีละคน",
                    (w // 2 - 120, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 80, 255),
                    2,
                )
                self.after(
                    0, lambda: self.sub_label.configure(text="⚠  กรุณาเข้าทีละคน")
                )

            elif len(faces) == 1:
                x, y, fw, fh = faces[0]
                pad = 20
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(w, x + fw + pad)
                y2 = min(h, y + fh + pad)

                cv2.rectangle(frame, (x, y), (x + fw, y + fh), (255, 200, 0), 2)
                cv2.ellipse(
                    frame, (cx, cy), (oval_a, oval_b), 0, 0, 360, (56, 189, 248), 2
                )

                crop = frame[y1:y2, x1:x2]
                if crop.size > 0:
                    self.is_scanning = True
                    self._last_faces = []
                    self.after(
                        0,
                        lambda: self.status_label.configure(
                            text="VERIFYING...", text_color=CLR["warning"]
                        ),
                    )
                    self.after(
                        0,
                        lambda: self.sub_label.configure(
                            text="กำลังตรวจสอบใบหน้าและสิทธิ์..."
                        ),
                    )

                    threading.Thread(
                        target=self._verify_pipeline,
                        args=(crop.copy(),),
                        daemon=True,
                    ).start()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        imgtk = ctk.CTkImage(
            light_image=Image.fromarray(rgb),
            dark_image=Image.fromarray(rgb),
            size=CONFIG["DISPLAY_SIZE"],
        )
        self.video_label.configure(image=imgtk, text="")
        self.video_label.image = imgtk

        self.after(30, self._display_loop)

    # ──────────────────────────────────────────────────────────────────────
    # VERIFICATION PIPELINE (Liveness + FaceNet Embedding Matching)
    # ──────────────────────────────────────────────────────────────────────

    def _verify_pipeline(self, face_crop):
        try:
            # 1. ตรวจสอบ Liveness ก่อน
            anti_crop = cv2.resize(face_crop, (80, 80))
            liveness_score = float(
                self.anti_spoof.predict(anti_crop, self.model_path)[0][1]
            )

            if liveness_score <= CONFIG["LIVENESS_THRESHOLD"]:
                self.after(0, self._show_liveness_denied, liveness_score)
                return

            # 2. หากเป็นคนจริง -> สกัด FaceNet Embedding
            img_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
            img_resized = cv2.resize(img_rgb, (160, 160))

            img_tensor = (
                torch.tensor(img_resized).permute(2, 0, 1).float().unsqueeze(0)
            )
            img_tensor = (img_tensor - 127.5) / 128.0

            with torch.no_grad():
                current_emb = self.facenet(img_tensor).numpy().flatten()

            # L2 Normalization
            norm = np.linalg.norm(current_emb)
            if norm > 0:
                current_emb = current_emb / norm

            if not self.known_face_embeddings:
                self.after(
                    0, self._show_unauthorized, "ไม่พบข้อมูลในระบบ", liveness_score
                )
                return

            # 3. คำนวณ Cosine Similarity
            similarities = [
                np.dot(current_emb, db_emb)
                for db_emb in self.known_face_embeddings
            ]
            best_idx = int(np.argmax(similarities))
            best_sim = float(similarities[best_idx])

            print(
                f"[Recognition] Best Match: {self.known_face_names[best_idx]} (Similarity: {best_sim:.3f})"
            )

            if best_sim >= CONFIG["SIMILARITY_THRESHOLD"]:
                user_name = self.known_face_names[best_idx]
                self.after(
                    0, self._show_granted, user_name, liveness_score, best_sim
                )
            else:
                self.after(
                    0,
                    self._show_unauthorized,
                    "ไม่มีสิทธิ์เข้าใช้งาน",
                    liveness_score,
                )

        except Exception as e:
            print(f"[Verification Pipeline Error]: {e}")
            traceback.print_exc()
            self.after(0, self._reset_state)

    # ──────────────────────────────────────────────────────────────────────
    # RESULT HANDLERS
    # ──────────────────────────────────────────────────────────────────────

    def _show_granted(self, user_name: str, l_score: float, sim: float):
        self.score_bar.set(l_score)
        self.score_pct_label.configure(text=f"{l_score*100:.0f}%")
        self._set_status("ACCESS GRANTED ✓", CLR["granted"], f"ยินดีต้อนรับ: {user_name}")
        self.score_badge.configure(
            text=f"  Match: {sim*100:.1f}%  ",
            fg_color="#0ea5e9",
            text_color="white",
        )
        self.score_bar.configure(progress_color=CLR["granted"])
        threading.Thread(
            target=lambda: [winsound.Beep(1000, 120), winsound.Beep(1200, 120)],
            daemon=True,
        ).start()
        self.after(CONFIG["RESET_DELAY_MS"], self._reset_state)

    def _show_unauthorized(self, reason: str, score: float):
        self.score_bar.set(score)
        self.score_pct_label.configure(text=f"{score*100:.0f}%")
        self._set_status("UNAUTHORIZED ✗", CLR["warning"], reason)
        self.score_badge.configure(
            text="  Face Not Registered  ",
            fg_color=CLR["warning"],
            text_color="black",
        )
        self.score_bar.configure(progress_color=CLR["warning"])
        threading.Thread(
            target=lambda: winsound.Beep(600, 300), daemon=True
        ).start()
        self.after(CONFIG["RESET_DELAY_MS"], self._reset_state)

    def _show_liveness_denied(self, score: float):
        self.score_bar.set(score)
        self.score_pct_label.configure(text=f"{score*100:.0f}%")
        self._set_status("ACCESS DENIED ✗", CLR["denied"], "ตรวจพบการหลอกลวง (Fake Face)")
        self.score_badge.configure(
            text=f"  Spoof ({score:.2f})  ",
            fg_color="#dc2626",
            text_color="white",
        )
        self.score_bar.configure(progress_color=CLR["denied"])
        threading.Thread(
            target=lambda: winsound.Beep(400, 600), daemon=True
        ).start()
        self.after(CONFIG["RESET_DELAY_MS"], self._start_cooldown)

    def _set_status(self, text: str, color: str, sub: str):
        self.status_label.configure(text=text, text_color=color)
        self.sub_label.configure(text=sub)

    # ──────────────────────────────────────────────────────────────────────
    # COOLDOWN & RESET
    # ──────────────────────────────────────────────────────────────────────

    def _start_cooldown(self):
        self.in_cooldown = True
        self._cooldown_left = CONFIG["SPOOF_COOLDOWN_SEC"]
        self.score_badge.configure(text="", fg_color="transparent")
        self.cooldown_frame.pack(padx=20, pady=8, fill="x")
        self._tick_cooldown()

    def _tick_cooldown(self):
        if self._cooldown_left > 0:
            self.cooldown_label.configure(
                text=f"🚫  ระบบล็อกชั่วคราว  {self._cooldown_left} วินาที"
            )
            self._cooldown_left -= 1
            self.after(1000, self._tick_cooldown)
        else:
            self.cooldown_frame.pack_forget()
            self.in_cooldown = False
            self._reset_state()

    def _reset_state(self):
        self._set_status("READY TO SCAN", CLR["ready"], "หันหน้าเข้าหากล้อง")
        self.score_badge.configure(text="", fg_color="transparent")
        self.score_bar.set(0)
        self.score_bar.configure(progress_color=CLR["ready"])
        self.score_pct_label.configure(text="—")
        self.is_scanning = False
        self._last_faces = []

    def on_closing(self):
        self.cap.release()
        self.destroy()


if __name__ == "__main__":
    app = GatekeeperDemo()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()