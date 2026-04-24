import cv2
import os
import sys
import numpy as np
import pickle
from deepface import DeepFace
from scipy.spatial.distance import cdist

# ==========================================
# 🎛️ CONFIGURATION (Bare Minimum Mode)
# ==========================================
CONFIG = {
    "LIVENESS_THRESHOLD": 0.72,
    "VERIFICATION_THRESHOLD": 0.50,
    "VERIFICATION_MODEL": "SFace",
    "FRAME_SKIP": 4, 
    "CACHE_FILE": "embeddings_cache.pkl",
    "KNOWN_FACES_DIR": "known_faces"
}

class FastGatekeeper:
    def __init__(self):
        self.known_embs = []
        self.known_names = []
        
        # 1. โหลด Anti-Spoofing อย่างรวดเร็ว
        repo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Silent-Face-Anti-Spoofing")
        sys.path.append(repo_path)
        self.model_path = os.path.join(repo_path, "resources", "anti_spoof_models", "2.7_80x80_MiniFASNetV2.pth")
        
        from src.anti_spoof_predict import AntiSpoofPredict
        orig_cwd = os.getcwd()
        os.chdir(repo_path)
        self.anti_spoof = AntiSpoofPredict(device_id=None) 
        os.chdir(orig_cwd)

        # 2. ตัวหาหน้าคนแบบดั้งเดิม (เร็วสุด)
        self.detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        # 3. โหลดความจำ (ถ้ามีไฟล์ Cache กล้องจะเปิดทันที)
        if os.path.exists(CONFIG["CACHE_FILE"]):
            with open(CONFIG["CACHE_FILE"], 'rb') as f:
                data = pickle.load(f)
                self.known_embs, self.known_names = data['embeddings'], data['names']
        else:
            self._build_cache()

    def _build_cache(self):
        print("⏳ สร้างไฟล์ความจำครั้งแรก (รอสักครู่)...")
        if not os.path.exists(CONFIG["KNOWN_FACES_DIR"]): os.makedirs(CONFIG["KNOWN_FACES_DIR"])
        embs, names = [], []
        for f in os.listdir(CONFIG["KNOWN_FACES_DIR"]):
            if f.lower().endswith(('.jpg', '.png', '.jpeg')):
                try:
                    res = DeepFace.represent(os.path.join(CONFIG["KNOWN_FACES_DIR"], f), model_name=CONFIG["VERIFICATION_MODEL"], enforce_detection=False)
                    embs.append(res[0]["embedding"])
                    names.append(os.path.splitext(f)[0])
                except: pass
        if embs:
            self.known_embs, self.known_names = np.array(embs), names
            with open(CONFIG["CACHE_FILE"], 'wb') as f:
                pickle.dump({'embeddings': self.known_embs, 'names': self.known_names}, f)

    def run(self):
        cap = cv2.VideoCapture(0)
        cap.set(3, 640) # Width
        cap.set(4, 480) # Height
        count = 0
        results = []
        
        print("🚀 ระบบพร้อม! กล้องทำงานแล้ว")
        while True:
            ret, frame = cap.read()
            if not ret: break
            frame = cv2.flip(frame, 1)
            count += 1

            if count % CONFIG["FRAME_SKIP"] == 0:
                results = []
                gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (0, 0), fx=0.5, fy=0.5)
                faces = self.detector.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))

                if len(faces) > 0:
                    x, y, w, h = max(faces, key=lambda r: r[2]*r[3])
                    x, y, w, h = x*2, y*2, w*2, h*2 # ขยายพิกัดกลับ
                    x, y = max(0, x-10), max(0, y-10)
                    w, h = min(frame.shape[1]-x, w+20), min(frame.shape[0]-y, h+20)
                    
                    crop = frame[y:y+h, x:x+w]
                    if crop.size > 0:
                        score = self.anti_spoof.predict(cv2.resize(crop, (80, 80)), self.model_path)[0][1]
                        name = "Unknown"
                        
                        # AI จะโหลดเฉพาะตอนที่สแกนเจอคนจริงครั้งแรกเท่านั้น (ข้ามการโหลดตอนเปิดเครื่อง)
                        if score > CONFIG["LIVENESS_THRESHOLD"] and len(self.known_embs) > 0:
                            try:
                                emb = DeepFace.represent(crop, model_name=CONFIG["VERIFICATION_MODEL"], enforce_detection=False)[0]["embedding"]
                                dists = cdist([emb], self.known_embs, metric='cosine')[0]
                                idx = np.argmin(dists)
                                if dists[idx] < CONFIG["VERIFICATION_THRESHOLD"]:
                                    name = self.known_names[idx]
                            except: pass
                            
                        results.append({"area": (x,y,w,h), "score": score, "name": name})

            # วาดผลลัพธ์
            for res in results:
                x, y, w, h = res["area"]
                is_real = res["score"] > CONFIG["LIVENESS_THRESHOLD"]
                color = (0, 255, 0) if is_real else (0, 0, 255)
                
                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                cv2.putText(frame, f"{'REAL' if is_real else 'FAKE'} ({res['score']:.2f})", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                if is_real: 
                    cv2.putText(frame, f"ID: {res['name']}", (x, y-30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            cv2.imshow('Gatekeeper (Bare Minimum)', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    Gatekeeper = FastGatekeeper()
    Gatekeeper.run()