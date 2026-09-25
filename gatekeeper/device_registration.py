"""Admin-assisted registration for a Smart Lab Gatekeeper camera."""

from __future__ import annotations

import json
import os
import platform
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import requests


DEFAULT_API_URL = "https://h0sh1na-smart-lab-backend.hf.space"
GATEKEEPER_DEVICE_PREFIX = "gatekeeper-"
GATEKEEPER_VERSION = os.getenv("SMART_GATEKEEPER_VERSION", "gatekeeper")[:64]


class RegistrationError(RuntimeError):
    """Safe, user-facing registration error."""


def normalize_api_url(api_url: str) -> str:
    normalized = str(api_url or "").strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise RegistrationError("กรุณากรอก Backend URL ที่ถูกต้อง โดยขึ้นต้นด้วย http:// หรือ https://")
    return normalized


def _response_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:300]
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message")
        return str(detail or "").strip()
    return ""


def _check_response(response: requests.Response, expected: set[int]) -> None:
    if response.status_code in expected:
        return
    raise RegistrationError(_response_detail(response) or f"Backend ตอบกลับ HTTP {response.status_code}")


def login_admin(
    api_url: str,
    email: str,
    password: str,
    *,
    client: Any = requests,
    timeout: int = 20,
) -> str:
    """Authenticate an Admin without persisting the password or access token."""
    try:
        response = client.post(
            f"{normalize_api_url(api_url)}/login",
            data={"username": email.strip(), "password": password},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RegistrationError(f"เชื่อมต่อ Backend ไม่สำเร็จ: {exc}") from exc
    _check_response(response, {200})
    try:
        token = str(response.json().get("access_token") or "").strip()
    except (AttributeError, ValueError):
        token = ""
    if not token:
        raise RegistrationError("Backend ไม่ได้ส่ง access token กลับมา")
    return token


def list_active_labs(
    api_url: str,
    access_token: str,
    *,
    client: Any = requests,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    try:
        response = client.get(
            f"{normalize_api_url(api_url)}/labs",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RegistrationError(f"โหลดรายชื่อ Lab ไม่สำเร็จ: {exc}") from exc
    _check_response(response, {200})
    try:
        rows = response.json().get("data", [])
    except (AttributeError, ValueError):
        rows = []
    if not isinstance(rows, list):
        raise RegistrationError("รูปแบบข้อมูล Lab จาก Backend ไม่ถูกต้อง")
    labs = [
        row for row in rows
        if isinstance(row, dict) and str(row.get("status") or "").lower() == "active"
    ]
    return sorted(labs, key=lambda row: str(row.get("code") or ""))


def build_device_payload(
    saved_registration: Optional[dict[str, Any]],
    api_url: str,
    device_name: str,
) -> dict[str, str]:
    backend_url = normalize_api_url(api_url)
    saved = saved_registration or {}
    saved_url = str(saved.get("api_url") or "").rstrip("/")
    saved_id = str(saved.get("device_id") or "").strip()
    if saved_url != backend_url or not saved_id.startswith(GATEKEEPER_DEVICE_PREFIX):
        saved_id = f"{GATEKEEPER_DEVICE_PREFIX}{uuid.uuid4().hex}"
    return {
        "device_id": saved_id,
        "device_name": str(device_name or "").strip() or platform.node() or "Smart Lab Gatekeeper",
        "agent_version": GATEKEEPER_VERSION,
    }


def register_gatekeeper_as_admin(
    api_url: str,
    access_token: str,
    lab_id: int,
    device_payload: dict[str, str],
    *,
    client: Any = requests,
    timeout: int = 20,
) -> dict[str, Any]:
    backend_url = normalize_api_url(api_url)
    try:
        response = client.post(
            f"{backend_url}/admin/lab-devices/register",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"lab_id": lab_id, **device_payload},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RegistrationError(f"ลงทะเบียนกล้องไม่สำเร็จ: {exc}") from exc
    _check_response(response, {200, 201})
    try:
        result = response.json()
    except ValueError as exc:
        raise RegistrationError("Backend ส่งผลการลงทะเบียนไม่ถูกต้อง") from exc
    if not isinstance(result, dict):
        raise RegistrationError("Backend ส่งผลการลงทะเบียนไม่ถูกต้อง")

    device = result.get("device") or {}
    lab = device.get("lab") or {}
    device_token = str(result.get("device_token") or "").strip()
    if not device_token:
        raise RegistrationError("Backend ไม่ได้ส่ง Device Credential กลับมา")
    return {
        "device_id": result.get("device_id") or device_payload["device_id"],
        "device_token": device_token,
        "api_url": backend_url,
        "lab_id": lab.get("id"),
        "lab_code": lab.get("code"),
        "lab_name": lab.get("name"),
        "device_name": device.get("device_name") or device_payload["device_name"],
        "agent_version": device.get("agent_version") or device_payload["agent_version"],
        "registered_at": device.get("created_at"),
    }


def registration_path() -> Path:
    configured_dir = os.getenv("SMART_GATEKEEPER_DATA_DIR")
    if configured_dir:
        base_dir = Path(configured_dir).expanduser()
    else:
        app_data = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        base_dir = (
            Path(app_data).expanduser() / "SmartLabGatekeeper"
            if app_data
            else Path.home() / ".smart_lab_gatekeeper"
        )
    return base_dir.resolve() / "device_registration.json"


def load_device_registration() -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(registration_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if not str(payload.get("device_id") or "").startswith(GATEKEEPER_DEVICE_PREFIX):
        return None
    if not str(payload.get("device_token") or "").strip():
        return None
    if not str(payload.get("api_url") or "").strip():
        return None
    return payload


def save_device_registration(payload: dict[str, Any]) -> Path:
    if not str(payload.get("device_id") or "").startswith(GATEKEEPER_DEVICE_PREFIX):
        raise ValueError("a Gatekeeper device_id is required")
    if not str(payload.get("device_token") or "").strip():
        raise ValueError("device_token is required")
    path = registration_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
