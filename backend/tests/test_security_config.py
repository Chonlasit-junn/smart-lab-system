import os
import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import security_config as config
from cors_middleware import OriginCheckedCORSMiddleware
import utils
from routers import users


class SecurityConfigTests(unittest.TestCase):
    def test_production_and_huggingface_require_private_key(self):
        for env in ({"SMART_LAB_ENV": "production"}, {"SPACE_ID": "owner/test"}, {"SMART_LAB_ENV": "staging"}):
            with self.assertRaises(RuntimeError):
                config.jwt_secret(env)
        with self.assertRaises(RuntimeError):
            config.jwt_secret({"SECRET_KEY": "too-short-private-value"})

    def test_valid_key_is_preserved_and_never_echoed_on_errors(self):
        key = "synthetic-existing-key-01234567890123456789"
        self.assertEqual(config.jwt_secret({"SMART_LAB_ENV": "production", "SECRET_KEY": key}), key)
        with self.assertRaises(RuntimeError) as caught:
            config.jwt_secret({"SECRET_KEY": "short-private-value"})
        self.assertNotIn("short-private-value", str(caught.exception))
        self.assertEqual(utils.SECRET_KEY, users.SECRET_KEY)
        self.assertEqual(utils.ALGORITHM, users.ALGORITHM)

    def test_dev_key_is_stable_only_for_current_process(self):
        self.assertEqual(config.jwt_secret({}), config.jwt_secret({}))
        self.assertGreaterEqual(len(config.jwt_secret({})), 32)

    def test_production_requires_exact_https_origins(self):
        for value in ("", "*", "https://*.example.com", "http://example.com", "https://example.com/path", "https://user:pass@example.com", "https://example.com?query=secret", "https://example.com:bad"):
            with self.subTest(value=value), self.assertRaises((RuntimeError, ValueError)):
                config.cors_origins({"SMART_LAB_ENV": "production", "CORS_ALLOWED_ORIGINS": value})
        self.assertEqual(config.cors_origins({"SMART_LAB_ENV": "production", "CORS_ALLOWED_ORIGINS": "https://web.example.com/, https://web.example.com"}), ["https://web.example.com"])

    def test_cors_allows_authorized_browser_and_rejects_other_preflight(self):
        app = FastAPI()
        app.add_middleware(OriginCheckedCORSMiddleware, allow_origins=config.cors_origins({"CORS_ALLOWED_ORIGINS": "https://web.example.com"}), allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])
        with TestClient(app) as client:
            for origin, status in (("https://web.example.com", 200), ("https://attacker.example.com", 403)):
                response = client.options("/login", headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Authorization, Content-Type"})
                self.assertEqual(response.status_code, status)
                if status == 200:
                    self.assertEqual(response.headers["access-control-allow-origin"], origin)
                else:
                    self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
