"""Shared device registration helpers used by setup tools."""

from __future__ import annotations

import os
import platform
import uuid
from typing import Any, Optional
from urllib.parse import urlsplit

import requests


DEFAULT_API_URL = "https://h0sh1na-smart-lab-backend.hf.space"
DEFAULT_AGENT_VERSION = os.getenv("SMART_LAB_AGENT_VERSION", "source")


class LabSetupError(RuntimeError):
    """A safe, user-facing provisioning error."""


def _response_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:300]

    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message")
        if isinstance(detail, (dict, list)):
            return str(detail)
        return str(detail or "").strip()
    return ""


def _raise_for_api_error(response: requests.Response, expected: set[int]) -> None:
    if response.status_code in expected:
        return
    detail = _response_detail(response) or f"HTTP {response.status_code}"
    raise LabSetupError(detail)


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
        raise LabSetupError("กรุณากรอก Backend URL ที่ถูกต้อง โดยขึ้นต้นด้วย http:// หรือ https://")
    return normalized


def _device_mac() -> str:
    return ":".join(f"{byte:02x}" for byte in uuid.getnode().to_bytes(6, "big"))


def build_device_payload(
    saved_registration: Optional[dict[str, Any]],
    device_name: str,
    agent_version: str = DEFAULT_AGENT_VERSION,
) -> dict[str, str]:
    saved = saved_registration or {}
    device_id = str(saved.get("device_id") or "").strip() or uuid.uuid4().hex
    resolved_name = device_name.strip() or platform.node() or "Smart Lab workstation"
    return {
        "device_id": device_id,
        "device_name": resolved_name,
        "device_mac": _device_mac(),
        "agent_version": agent_version.strip()[:64] or "source",
    }


def build_device_payload_for_api(
    saved_registration: Optional[dict[str, Any]],
    api_url: str,
    device_name: str,
    agent_version: str = DEFAULT_AGENT_VERSION,
) -> dict[str, str]:
    """Reuse a saved device id only when it belongs to this Backend."""

    backend_url = normalize_api_url(api_url)
    saved = saved_registration or {}
    saved_url = str(saved.get("api_url") or "").rstrip("/")
    if saved_url and saved_url != backend_url:
        saved = {}
    return build_device_payload(saved, device_name, agent_version)


def _registration_result(
    response: requests.Response,
    backend_url: str,
    device_payload: dict[str, str],
) -> dict[str, Any]:
    _raise_for_api_error(response, {200, 201})
    try:
        result = response.json()
    except ValueError as exc:
        raise LabSetupError("Backend ส่งผลลัพธ์การลงทะเบียนไม่ถูกต้อง") from exc
    if not isinstance(result, dict):
        raise LabSetupError("Backend ส่งผลลัพธ์การลงทะเบียนไม่ถูกต้อง")

    device = result.get("device") or {}
    lab = device.get("lab") or {}
    device_token = str(result.get("device_token") or "").strip()
    if not device_token:
        raise LabSetupError("Backend ไม่ได้ส่ง Device Token กลับมา")

    return {
        "device_id": result.get("device_id") or device_payload["device_id"],
        "device_token": device_token,
        "api_url": backend_url,
        "lab_id": lab.get("id"),
        "lab_code": lab.get("code"),
        "lab_name": lab.get("name"),
        "device_name": device.get("device_name") or device_payload["device_name"],
        "device_mac": device.get("device_mac") or device_payload["device_mac"],
        "agent_version": device.get("agent_version") or device_payload["agent_version"],
        "registered_at": device.get("created_at"),
    }


def register_device_as_admin(
    api_url: str,
    access_token: str,
    lab_id: int,
    device_payload: dict[str, str],
    *,
    client: Any = requests,
    timeout: int = 20,
) -> dict[str, Any]:
    """Register a workstation directly with the authenticated Admin session."""

    backend_url = normalize_api_url(api_url)
    try:
        response = client.post(
            f"{backend_url}/admin/lab-devices/register",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"lab_id": lab_id, **device_payload},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise LabSetupError(f"ลงทะเบียนเครื่องไม่สำเร็จ: {exc}") from exc

    return _registration_result(response, backend_url, device_payload)
