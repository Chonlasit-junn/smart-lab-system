"""Non-secret local camera selection, separate from device credentials."""

import json

from device_registration import registration_path


def load_camera_index(default=0):
    try:
        path = registration_path().with_name("camera_preferences.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        index = payload.get("camera_index") if isinstance(payload, dict) else None
        return index if type(index) is int and 0 <= index < 6 else default
    except (OSError, ValueError):
        return default


def save_camera_index(index):
    if type(index) is not int or not 0 <= index < 6:
        raise ValueError("Invalid camera index")
    path = registration_path().with_name("camera_preferences.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps({"camera_index": index}), encoding="utf-8")
    pending.replace(path)
