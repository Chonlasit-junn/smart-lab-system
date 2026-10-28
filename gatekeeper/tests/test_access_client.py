import json
import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np
import requests

from access_client import DENIAL_MESSAGES, ScanClient, verify_scan


def response(status, payload):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode("utf-8")
    return result


class AccessClientTests(unittest.TestCase):
    def setUp(self):
        self.registration = {
            "device_id": "gatekeeper-client-test", "device_token": "synthetic-token",
            "lab_code": "LAB01",
        }
        self.frame = np.zeros((80, 80, 3), dtype=np.uint8)

    def verify(self, result, **kwargs):
        client = Mock()
        client.post.return_value = result
        accepted, detail = verify_scan(
            "https://backend.example/", self.registration, self.frame, 0.90, client=client, **kwargs,
        )
        return accepted, detail, client

    def test_explicit_authorization_and_audit_receipt_allow_access(self):
        accepted, detail, client = self.verify(response(200, {
            "access_granted": True, "scan_id": 42, "user_name": "Test User",
        }))
        self.assertTrue(accepted)
        self.assertEqual(detail, "Test User")
        self.assertEqual(client.post.call_args.args[0], "https://backend.example/gatekeeper/identify")
        request = client.post.call_args.kwargs
        self.assertEqual(request["data"]["device_id"], self.registration["device_id"])
        self.assertEqual(request["data"]["liveness_passed"], "true")
        self.assertEqual(request["files"]["face_image"][2], "image/jpeg")

    def test_old_identity_only_backend_does_not_grant_access(self):
        accepted, detail, _client = self.verify(response(200, {
            "message": "Face identity verified.", "user_id": 1, "user_name": "Test User",
        }))
        self.assertFalse(accepted)
        self.assertIn("อัปเดตระบบ", detail)

    def test_false_or_missing_receipt_cannot_grant_access(self):
        for scan_id in (None, 0, -1, True, "42"):
            with self.subTest(scan_id=scan_id):
                accepted, _detail, _client = self.verify(response(200, {
                    "access_granted": True, "scan_id": scan_id, "user_name": "Test User",
                }))
                self.assertFalse(accepted)
        accepted, _detail, _client = self.verify(response(200, {
            "access_granted": False, "scan_id": 42, "user_name": "Test User",
        }))
        self.assertFalse(accepted)

    def test_denial_codes_have_readable_thai_messages(self):
        for code in ("booking_required", "guest_approval_required", "user_banned", "scan_history_unavailable"):
            with self.subTest(code=code):
                accepted, detail, _client = self.verify(response(403, {
                    "detail": {"code": code, "message": "Server message", "scan_id": 42},
                }))
                self.assertFalse(accepted)
                self.assertEqual(detail, DENIAL_MESSAGES[code])

    def test_local_liveness_failure_is_reported_without_sending_a_photo(self):
        client = Mock()
        client.post.return_value = response(403, {
            "detail": {"code": "liveness_no_motion", "scan_id": 42},
        })
        accepted, detail = verify_scan(
            "https://backend.example", self.registration, None, 0.95,
            liveness_passed=False, liveness_reason="no_motion", client=client,
        )
        self.assertFalse(accepted)
        self.assertEqual(detail, DENIAL_MESSAGES["liveness_no_motion"])
        request = client.post.call_args.kwargs
        self.assertNotIn("files", request)
        self.assertEqual(request["data"]["liveness_passed"], "false")
        self.assertEqual(request["data"]["liveness_reason"], "no_motion")

    def test_server_response_cannot_override_local_liveness_rejection(self):
        accepted, _detail, _client = self.verify(response(200, {
            "access_granted": True, "scan_id": 42, "user_name": "Test User",
        }), liveness_passed=False)
        self.assertFalse(accepted)

    def test_missing_registration_cannot_make_an_access_request(self):
        client = Mock()
        accepted, _detail = verify_scan("https://backend.example", None, self.frame, 0.90, client=client)
        self.assertFalse(accepted)
        client.post.assert_not_called()

    def test_network_failure_denies_access_and_reports_missing_history(self):
        client = Mock()
        client.post.side_effect = requests.Timeout()
        accepted, detail = verify_scan(
            "https://backend.example", self.registration, self.frame, 0.90, client=client,
        )
        self.assertFalse(accepted)
        self.assertIn("ยืนยันการบันทึกประวัติไม่ได้", detail)

    def test_malformed_response_cannot_grant_access(self):
        for payload in (None, [], "granted"):
            with self.subTest(payload=payload):
                accepted, _detail, _client = self.verify(response(200, payload))
                self.assertFalse(accepted)

    def test_persistent_client_reuses_session_and_closes_once_without_retrying_post(self):
        with patch("access_client.requests.Session") as factory:
            client = ScanClient()
            session = factory.return_value
            session.post.return_value = response(200, {
                "access_granted": True, "scan_id": 1, "user_name": "Synthetic User",
            })
            for _ in range(2):
                self.assertTrue(client.verify("https://backend.example", self.registration, self.frame, 0.9)[0])
            factory.assert_called_once()
            self.assertEqual(session.post.call_count, 2)
            adapter = session.mount.call_args.args[1]
            self.assertEqual(adapter.max_retries.total, 0)
            client.close()
            client.close()
            session.close.assert_called_once()
            self.assertFalse(client.verify("https://backend.example", self.registration, self.frame, 0.9)[0])
            self.assertEqual(session.post.call_count, 2)

    def test_timeout_sends_once_and_does_not_return_an_optimistic_grant(self):
        with patch("access_client.requests.Session") as factory:
            client = ScanClient()
            factory.return_value.post.side_effect = requests.Timeout()
            self.assertFalse(client.verify("https://backend.example", self.registration, self.frame, 0.9)[0])
            factory.return_value.post.assert_called_once()
            client.close()

    def test_scan_waiting_for_transport_does_not_send_after_shutdown(self):
        with patch("access_client.requests.Session") as factory:
            client = ScanClient()
            stop = threading.Event()
            result = []
            with client._lock:
                worker = threading.Thread(target=lambda: result.append(client.verify(
                    "https://backend.example", self.registration, self.frame, 0.9, stop_event=stop,
                )))
                worker.start()
                stop.set()
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertFalse(result[0][0])
            factory.return_value.post.assert_not_called()
            client.close()


if __name__ == "__main__":
    unittest.main()
