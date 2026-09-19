import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab_setup import (  # noqa: E402
    build_device_payload,
    create_enrollment_code,
    list_active_labs,
    login_admin,
    register_device_with_code,
)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/login"):
            return FakeResponse(200, {"access_token": "admin-token"})
        if url.endswith("/admin/lab-devices/enrollment-codes"):
            return FakeResponse(200, {"enrollment_code": "SETUP-CODE"})
        if url.endswith("/agent/register-device"):
            return FakeResponse(
                200,
                {
                    "device_id": kwargs["data"]["device_id"],
                    "device_token": "device-token",
                    "device": {
                        "device_name": kwargs["data"]["device_name"],
                        "device_mac": kwargs["data"]["device_mac"],
                        "agent_version": "source",
                        "lab": {"id": 1, "code": "LAB01", "name": "Main Lab"},
                    },
                },
            )
        return FakeResponse(404, {"detail": "unknown endpoint"})

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return FakeResponse(
            200,
            {
                "data": [
                    {"id": 2, "code": "LAB02", "name": "Closed Lab", "status": "maintenance"},
                    {"id": 1, "code": "LAB01", "name": "Main Lab", "status": "active"},
                ]
            },
        )


class LabSetupApiTests(unittest.TestCase):
    def test_existing_auth_flow_can_load_and_register_a_device(self):
        client = FakeClient()

        token = login_admin("http://backend/", "admin@example.com", "secret", client=client)
        labs = list_active_labs("http://backend/", token, client=client)
        code = create_enrollment_code("http://backend/", token, labs[0]["id"], client=client)
        payload = build_device_payload(
            {"device_id": "existing-device"},
            "Lab PC 01",
            agent_version="test",
        )
        registration = register_device_with_code(
            "http://backend/",
            code,
            payload,
            client=client,
        )

        self.assertEqual(token, "admin-token")
        self.assertEqual([lab["code"] for lab in labs], ["LAB01"])
        self.assertEqual(code, "SETUP-CODE")
        self.assertEqual(payload["device_id"], "existing-device")
        self.assertEqual(registration["device_token"], "device-token")
        self.assertEqual(registration["lab_code"], "LAB01")

        login_call = client.calls[0]
        self.assertEqual(login_call[2]["data"]["username"], "admin@example.com")
        self.assertEqual(login_call[2]["data"]["password"], "secret")
        self.assertEqual(
            client.calls[2][2]["json"],
            {"lab_id": 1, "expires_in_minutes": 5},
        )

    def test_new_device_id_is_created_when_registration_has_none(self):
        payload = build_device_payload(None, "Lab PC 02", agent_version="source")

        self.assertTrue(payload["device_id"])
        self.assertEqual(payload["device_name"], "Lab PC 02")
        self.assertEqual(payload["agent_version"], "source")
        self.assertTrue(payload["device_mac"])


if __name__ == "__main__":
    unittest.main()
