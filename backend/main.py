from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer

import models
from database import engine

# Import Routers ที่เพิ่งสร้าง
from routers import auth, labs, agent

# สร้างตารางใน Database (ถ้ายังไม่มี)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Smart Lab API")

# ตั้งค่า CORS ให้ Frontend ยิง API มาได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# เสียบปลั๊ก Router เข้าสู่ระบบหลัก
app.include_router(auth.router)
app.include_router(labs.router)
app.include_router(agent.router)

@app.get("/")
def root():
    return {"message": "Welcome to Smart Lab API"}