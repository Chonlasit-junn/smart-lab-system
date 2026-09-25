import os
import tempfile
import unittest
from unittest.mock import patch

from device_registration import (
    GATEKEEPER_DEVICE_PREFIX,
    RegistrationError,
    build_device_payload,
    load_device_registration,
    normalize_api_url,
    register_gatekeeper_as_admin,
    save_device_registration,
)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.request = None

    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return self.response


class GatekeeperRegistrationTests(unittest.TestCase):
    def test_payload_reuses_gatekeeper_id_only_for_same_backend(self):
        saved = {
            "api_url": "https://backend.example",
            "device_id": "gatekeeper-camera-001",
        }

        payload = build_device_payload(saved, "https://backend.example/", "Front Camera")

        self.assertEqual(payload["device_id"], "gatekeeper-camera-001")
        self.assertEqual(payload["device_name"], "Front Camera")
        self.assertTrue(payload["agent_version"].startswith("gatekeeper"))

        other_backend = build_device_payload(saved, "https://other.example", "Front Camera")
        self.assertTrue(other_backend["device_id"].startswith(GATEKEEPER_DEVICE_PREFIX))
        self.assertNotEqual(other_backend["device_id"], saved["device_id"])

    def test_invalid_api_url_is_rejected(self):
        with self.assertRaises(RegistrationError):
            normalize_api_url("https://user:password@example.com")

    def test_register_sends_admin_bearer_and_saves_only_device_credential(self):
        client = FakeClient(FakeResponse(201, {
            "device_id": "gatekeeper-camera-002",
            "device_token": "device-secret",
            "device": {
                "device_name": "Entrance Camera",
                "agent_version": "gatekeeper",
                "created_at": "2026-09-25T10:00:00Z",
                "lab": {"id": 3, "code": "LAB03", "name": "Lab 3"},
            },
        }))
        payload = build_device_payload(None, "https://backend.example", "Entrance Camera")

        registration = register_gatekeeper_as_admin(
            "https://backend.example",
            "admin-access-token",
            3,
            payload,
            client=client,
        )

        self.assertEqual(registration["device_id"], "gatekeeper-camera-002")
        self.assertEqual(registration["lab_code"], "LAB03")
        self.assertNotIn("admin-access-token", str(registration))
        url, request = client.request
        self.assertEqual(url, "https://backend.example/admin/lab-devices/register")
        self.assertEqual(request["headers"]["Authorization"], "Bearer admin-access-token")
        self.assertEqual(request["json"]["lab_id"], 3)

    def test_registration_storage_is_scoped_to_gatekeeper_data_dir(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"SMART_GATEKEEPER_DATA_DIR": directory},
        ):
            registration = {
                "device_id": "gatekeeper-camera-003",
                "device_token": "device-secret",
                "api_url": "https://backend.example",
                "lab_code": "LAB03",
            }

            save_device_registration(registration)

            self.assertEqual(load_device_registration(), registration)


if __name__ == "__main__":
    unittest.main()
