import os
import json
import sqlite3
from pathlib import Path
from .logger import logger

DATA_DIR = Path(os.getenv("APPDATA", ".")) / "SmartLabAgent"
DATA_DIR.mkdir(parents=True, exist_ok=True)

class PendingLogStore:
    """เก็บ usage logs ลง SQLite ก่อนส่ง — ป้องกัน data loss เมื่อ network ล้มเหลว."""

    def __init__(self, db_path: Path = None):
        self._db_path = db_path or (DATA_DIR / "pending_logs.db")
        self._ensure_table()

    def _connect(self):
        return sqlite3.connect(str(self._db_path), timeout=5)

    def _ensure_table(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_logs (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT    NOT NULL,
                    usage_data TEXT    NOT NULL,
                    hostname   TEXT    DEFAULT '',
                    mac_address TEXT   DEFAULT '',
                    created_at TEXT    DEFAULT (datetime('now','localtime'))
                )
            """)
            # Migration: เพิ่ม column ใหม่ถ้า DB เก่ายังไม่มี
            existing = {row[1] for row in conn.execute("PRAGMA table_info(pending_logs)")}
            if "hostname" not in existing:
                conn.execute("ALTER TABLE pending_logs ADD COLUMN hostname TEXT DEFAULT ''")
            if "mac_address" not in existing:
                conn.execute("ALTER TABLE pending_logs ADD COLUMN mac_address TEXT DEFAULT ''")

    def save(self, session_id: str, summary: list,
             hostname: str = "", mac_address: str = "") -> int:
        """บันทึก log ลง local DB ก่อนส่ง — return row id."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO pending_logs (session_id, usage_data, hostname, mac_address) VALUES (?, ?, ?, ?)",
                (session_id, json.dumps(summary, ensure_ascii=False), hostname, mac_address),
            )
            row_id = cur.lastrowid
            logger.info(f"Saved pending log id={row_id} for session={session_id} device={hostname}")
            return row_id

    def delete(self, row_id: int):
        """ลบ log ที่ส่งสำเร็จแล้ว."""
        with self._connect() as conn:
            conn.execute("DELETE FROM pending_logs WHERE id = ?", (row_id,))
            logger.info(f"Deleted pending log id={row_id}")

    def get_all_pending(self) -> list:
        """ดึง logs ที่ยังค้างส่งทั้งหมด — return list of (id, session_id, usage_data_json, hostname, mac_address)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, session_id, usage_data, hostname, mac_address FROM pending_logs ORDER BY id"
            ).fetchall()
            return rows
