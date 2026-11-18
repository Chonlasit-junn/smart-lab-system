"""Local storage for the workstation registration returned by the Backend."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


INSTALL_SETTINGS_KEY = r"Software\Smart Lab\Device Agent"


def installed_agent_setting(name: str) -> str | None:
    """Read an administrator-selected setting from the 64-bit MSI registry."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, INSTALL_SETTINGS_KEY, 0,
            winreg.KEY_QUERY_VALUE | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, kind = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return value if kind == winreg.REG_SZ else None


def get_agent_data_dir() -> Path:
    configured_dir = os.getenv("SMART_LAB_AGENT_DATA_DIR")
    if configured_dir:
        return Path(configured_dir).expanduser().resolve() / "SmartLabAgent"

    base_dir = (
        os.getenv("LOCALAPPDATA")
        or os.getenv("APPDATA")
        or os.path.join(os.path.expanduser("~"), ".smart_lab_agent")
    )
    return Path(base_dir).expanduser().resolve() / "SmartLabAgent"


def registration_path() -> Path:
    return get_agent_data_dir() / "device_registration.json"


def append_agent_diagnostic(file_name: str, detail: str) -> None:
    """Append bounded local diagnostics without including user or app data."""
    try:
        log_path = get_agent_data_dir() / file_name
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if log_path.exists() and log_path.stat().st_size > 64 * 1024:
            log_path.write_text("", encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as log_file:
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            log_file.write(f"{timestamp} {detail}\n")
    except OSError:
        pass


def load_device_registration() -> Optional[dict[str, Any]]:
    path = registration_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    if not str(payload.get("device_id") or "").strip():
        return None
    if not str(payload.get("device_token") or "").strip():
        return None
    return payload


def save_device_registration(payload: dict[str, Any]) -> Path:
    device_id = str(payload.get("device_id") or "").strip()
    device_token = str(payload.get("device_token") or "").strip()
    if not device_id or not device_token:
        raise ValueError("device_id and device_token are required")

    data_dir = get_agent_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    path = registration_path()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
