import os
import socket
import uuid
from .logger import logger

# ── CONFIG ────────────────────────────────────────────────────────────────────
API_URL    = "https://h0sh1na-smart-lab-backend.hf.space"
LAB_CODE   = "LAB01"
DEBUG_MODE = True   # ← เปลี่ยนเป็น False ก่อน deploy จริง
DEVICE_NAME = socket.gethostname()
DEVICE_MAC = ':'.join(f'{b:02x}' for b in uuid.getnode().to_bytes(6, 'big'))

logger.info(f"Device: {DEVICE_NAME} (MAC: {DEVICE_MAC})")

IGNORE_SYSTEM_APPS = [
    "Taskbar", "Program Manager", "Settings",
    "Windows Default Lock Screen", "Search",
]
