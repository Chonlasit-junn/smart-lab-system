import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from device_registration import build_device_payload_for_api  # noqa: E402


class DeviceRegistrarTests(unittest.TestCase):
    def test_backend_switch_does_not_reuse_an_id_from_the_old_backend(self):
        payload = build_device_payload_for_api(
            {
                "api_url": "https://old.example",
                "device_id": "old-device-id",
            },
            "https://new.example/",
            "Lab PC 02",
            agent_version="test",
        )

        self.assertNotEqual(payload["device_id"], "old-device-id")
        self.assertEqual(payload["device_name"], "Lab PC 02")
        self.assertEqual(payload["agent_version"], "test")

    def test_same_backend_keeps_the_existing_device_id(self):
        payload = build_device_payload_for_api(
            {
                "api_url": "https://backend.example/",
                "device_id": "existing-device-id",
            },
            "https://backend.example",
            "Lab PC 02",
        )

        self.assertEqual(payload["device_id"], "existing-device-id")


if __name__ == "__main__":
    unittest.main()
