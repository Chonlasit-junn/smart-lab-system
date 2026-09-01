import sys
import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ป้องกัน crash: .pyw / windowed .exe จะมี sys.stdout = None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

LOG_DIR = Path(os.getenv("APPDATA", ".")) / "SmartLabAgent" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("SmartLabAgent")
logger.setLevel(logging.DEBUG)

_file_handler = RotatingFileHandler(
    LOG_DIR / "agent.log",
    maxBytes=2 * 1024 * 1024,   # 2 MB per file
    backupCount=5,              # keep 5 rotated files
    encoding="utf-8",
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logger.addHandler(_file_handler)

# console handler เฉพาะตอน dev (stdout ใช้งานได้จริง)
if sys.stdout is not None and hasattr(sys.stdout, "fileno"):
    try:
        sys.stdout.fileno()  # จะ raise ถ้าเป็น devnull redirect
        _console_handler = logging.StreamHandler(sys.stdout)
        _console_handler.setLevel(logging.INFO)
        _console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(_console_handler)
    except (OSError, ValueError):
        pass

logger.info("Smart Lab Agent starting up...")
