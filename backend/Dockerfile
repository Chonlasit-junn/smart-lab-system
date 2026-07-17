# ใช้ Python 3.11 เป็นฐาน
FROM python:3.11-slim

# ติดตั้งเครื่องมือพื้นฐานที่จำเป็นสำหรับคอมไพล์ C++ (dlib) และ OpenCV
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 🌟 เพิ่มคำสั่งเวทมนตร์ตรงนี้! บังคับให้ Build ทีละ 1 คิว ป้องกัน RAM ทะลุ
ENV CMAKE_BUILD_PARALLEL_LEVEL=1
ENV MAX_JOBS=1

# คัดลอกและติดตั้งไลบรารีทั้งหมด
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกโค้ดทั้งหมดลงในกล่อง
COPY . .

# Hugging Face บังคับให้เซิร์ฟเวอร์ต้องรันบนพอร์ต 7860
EXPOSE 7860

# คำสั่งเปิดเซิร์ฟเวอร์ FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]