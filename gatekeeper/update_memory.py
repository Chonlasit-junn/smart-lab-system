import os
import pickle
from deepface import DeepFace

print("🧠 เริ่มต้นอัปเดตความจำให้ AI...")

KNOWN_DIR = "known_faces"
CACHE_FILE = "embeddings_cache.pkl"
MODEL_NAME = "SFace"

known_embs = []
known_names = []

if not os.path.exists(KNOWN_DIR):
    os.makedirs(KNOWN_DIR)
    print(f"สร้างโฟลเดอร์ {KNOWN_DIR} แล้ว กรุณาเอารูปไปใส่")

# วนอ่านรูปภาพทั้งหมดในโฟลเดอร์
for file in os.listdir(KNOWN_DIR):
    if file.lower().endswith(('.png', '.jpg', '.jpeg')):
        img_path = os.path.join(KNOWN_DIR, file)
        # ตัดนามสกุลไฟล์ออก (เช่น nlove0025@gmail.com.jpg -> nlove0025@gmail.com)
        email_name = os.path.splitext(file)[0]
        
        print(f"กำลังเรียนรู้ใบหน้าของ: {email_name}")
        try:
            # สกัดจุดเด่นบนใบหน้าเป็นตัวเลข
            result = DeepFace.represent(img_path, model_name=MODEL_NAME, enforce_detection=False)
            known_embs.append(result[0]["embedding"])
            known_names.append(email_name)
        except Exception as e:
            print(f"⚠️ ข้ามไฟล์ {file} เนื่องจาก: หาใบหน้าไม่เจอ หรือรูปไม่ชัด")

# บันทึกความจำลงไฟล์ .pkl ทับของเดิม
with open(CACHE_FILE, 'wb') as f:
    pickle.dump({'embeddings': known_embs, 'names': known_names}, f)

print(f"✅ อัปเดตความจำเสร็จสิ้น! ตอนนี้ AI รู้จักคนทั้งหมด {len(known_names)} คนแล้ว")