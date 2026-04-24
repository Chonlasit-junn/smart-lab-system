# Smart Lab Management System

ระบบจัดการและจองห้องปฏิบัติการ (Lab) อัจฉริยะ 
แบ่งเป็น 2 ส่วน: Frontend (React) และ Backend (FastAPI)

## วิธีการรันโปรเจกต์ (How to run)

### 1. รัน Backend (FastAPI)
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload

### 2. รัน Frontend (React)
cd frontend
npm install
npm run dev