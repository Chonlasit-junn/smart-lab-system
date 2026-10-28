import concurrent.futures
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import login_security as security
from routers import auth


class LoginSecurityTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.limiter = security.LoginLimiter(clock=lambda: self.now)

    def test_account_budget_is_canonical_across_ips_and_recovers(self):
        for i in range(10):
            self.limiter.check(f"10.0.0.{i}", " TEST@example.com ")
        with self.assertRaises(HTTPException) as caught:
            self.limiter.check("10.1.0.1", "test@example.com")
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.headers["Retry-After"], "300")
        self.now = 300
        self.limiter.check("10.1.0.1", "test@example.com")
        self.assertNotIn("test@example.com", str(self.limiter.entries))

    def test_ip_and_global_budgets_apply_to_distinct_accounts(self):
        for i in range(60):
            self.limiter.check("127.0.0.1", f"user{i}@example.invalid")
        with self.assertRaises(HTTPException):
            self.limiter.check("127.0.0.1", "new@example.invalid")
        for i in range(240):
            self.limiter.check(f"10.0.{i // 255}.{i % 255}", f"other{i}@example.invalid")
        with self.assertRaises(HTTPException):
            self.limiter.check("10.9.9.9", "last@example.invalid")
        self.now = 60
        self.limiter.check("10.9.9.9", "last@example.invalid")

    def test_memory_full_fails_closed_instead_of_evicting_live_budget(self):
        limiter = security.LoginLimiter(clock=lambda: self.now, max_entries=3)
        limiter.check("127.0.0.1", "test@example.invalid")
        with self.assertRaises(HTTPException):
            limiter.check("127.0.0.2", "other@example.invalid")
        self.assertEqual(len(limiter.entries), 3)
        self.now = 300
        limiter.check("127.0.0.2", "other@example.invalid")

    def test_parallel_attempts_do_not_exceed_account_budget(self):
        def attempt(_):
            try:
                self.limiter.check("127.0.0.1", "test@example.invalid")
                return 1
            except HTTPException:
                return 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            self.assertEqual(sum(pool.map(attempt, range(30))), 10)

    def test_http_limit_runs_before_lookup_and_does_not_trust_forwarded_headers(self):
        app = FastAPI()
        app.include_router(auth.router)
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        app.dependency_overrides[auth.get_db] = lambda: db
        with patch.object(security, "login_limiter", self.limiter), patch.object(auth, "password_matches", return_value=False), TestClient(app) as client:
            for i in range(10):
                response = client.post("/login", data={"username": " User@example.invalid ", "password": "wrong-password"}, headers={"X-Forwarded-For": f"10.0.0.{i}"})
                self.assertEqual(response.status_code, 401)
            db.reset_mock()
            response = client.post("/login", data={"username": "user@example.invalid", "password": "wrong-password"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers["Retry-After"], "300")
            db.query.assert_not_called()

    def test_unknown_and_wrong_credentials_use_same_error(self):
        db = Mock()
        for user in (None, SimpleNamespace(password="synthetic-hash")):
            db.query.return_value.filter.return_value.first.return_value = user
            with patch.object(auth, "password_matches", return_value=False), self.assertRaises(HTTPException) as caught:
                auth.login(SimpleNamespace(username="test@example.invalid", password="wrong-password"), db)
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (401, security.INVALID_LOGIN))

    def test_unknown_account_still_verifies_a_password_hash(self):
        with patch.object(security, "_dummy_hash", return_value="dummy"), patch.object(security.pwd_context, "verify", return_value=True) as verify:
            self.assertFalse(security.password_matches("test-password", None))
            verify.assert_called_once_with("test-password", "dummy")

    def test_invalid_hash_and_oversized_password_fail_without_server_error(self):
        with patch.object(security.pwd_context, "verify", side_effect=ValueError("bad hash")) as verify:
            self.assertFalse(security.password_matches("test-password", "bad"))
            verify.reset_mock()
            self.assertFalse(security.password_matches("ก" * 25, "bad"))
            verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
