"""Recovery tests use only in-memory SQLite and a mocked mail provider."""
import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import models
import otp_service as otp
import schemas
from database import Base
from routers import auth, password_reset as reset, users
from utils import create_access_token, pwd_context


@compiles(JSONB, "sqlite")
def compile_jsonb(_type, _compiler, **_kwargs):
    return "TEXT"


class PasswordResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_hash = pwd_context.hash("Old-test-password1!")

    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.now = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)
        self.clock = patch.object(otp, "utc_now", side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.key = patch.dict(os.environ, {"OTP_SECRET_KEY": "synthetic-only-012345678901234567890123"})
        self.key.start()
        self.addCleanup(self.key.stop)
        self.email = "reset@example.com"
        self.user = models.User(email=self.email, password=self.old_hash, first_name="Test", last_name="Recovery")
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def issue(self, email=None, delivered=True):
        email = email or self.email
        challenge, code, exists = reset._reserve(self.db, email)
        if delivered:
            otp.finish_delivery(self.db, email, challenge, success=exists, purpose=reset.PURPOSE)
        return challenge, code

    def row(self):
        return self.db.get(models.PasswordResetOTP, self.email, populate_existing=True)

    def confirm(self, code, password="New-test-password2!"):
        return reset.confirm(schemas.PasswordReset(email=self.email, otp=code, new_password=password), self.db)

    def test_hash_only_separate_table_and_purpose(self):
        challenge, code = self.issue()
        row = self.row()
        self.assertEqual(len(row.code_hash), 64)
        self.assertNotEqual(row.code_hash, code)
        self.assertNotEqual(row.code_hash, otp._digest(self.email, challenge, code))
        with self.assertRaises(HTTPException):
            otp.verify_otp(self.db, self.email, code)
        self.assertEqual(reset._verify(self.db, self.email, code), challenge)
        self.assertIsNone(self.row().consumed_at)

    def test_registration_code_cannot_reset_password(self):
        challenge, code = otp.reserve_otp(self.db, self.email)
        otp.finish_delivery(self.db, self.email, challenge, success=True)
        with self.assertRaises(HTTPException):
            self.confirm(code)
        self.assertEqual(self.db.get(models.User, self.user.id).password, self.old_hash)

    def test_success_changes_only_password_and_auth_version_and_blocks_replay(self):
        _, code = self.issue()
        self.confirm(code)
        self.db.refresh(self.user)
        self.assertTrue(pwd_context.verify("New-test-password2!", self.user.password))
        self.assertFalse(pwd_context.verify("Old-test-password1!", self.user.password))
        self.assertEqual(self.user.auth_version, 1)
        self.assertEqual(self.user.first_name, "Test")
        self.assertIsNotNone(self.row().consumed_at)
        with self.assertRaises(HTTPException):
            self.confirm(code)

    def test_wrong_guesses_persist_and_resending_does_not_clear_window(self):
        _, code = self.issue()
        wrong = "000000" if code != "000000" else "111111"
        for expected in range(1, 6):
            with self.assertRaises(HTTPException) as caught:
                reset._verify(self.db, self.email, wrong)
            self.assertEqual(self.row().window_attempts, expected)
        self.assertEqual(caught.exception.status_code, 429)
        self.now += timedelta(seconds=61)
        with self.assertRaises(HTTPException) as caught:
            self.issue()
        self.assertEqual(caught.exception.status_code, 429)
        self.now += timedelta(seconds=600)
        self.issue()
        self.assertEqual(self.row().window_attempts, 0)

    def test_resend_replaces_code_and_preserves_wrong_budget(self):
        with patch.object(otp.secrets, "randbelow", return_value=123456):
            _, old = self.issue()
        with self.assertRaises(HTTPException):
            reset._verify(self.db, self.email, "999999")
        with self.assertRaises(HTTPException) as caught:
            self.issue()
        self.assertEqual(caught.exception.headers["Retry-After"], "60")
        self.now += timedelta(seconds=60)
        with patch.object(otp.secrets, "randbelow", return_value=654321):
            _, latest = self.issue()
        self.assertEqual(self.row().window_attempts, 1)
        with self.assertRaises(HTTPException):
            reset._verify(self.db, self.email, old)
        reset._verify(self.db, self.email, latest)

    def test_expired_or_pending_cannot_reset(self):
        _, code = self.issue(delivered=False)
        with self.assertRaises(HTTPException):
            self.confirm(code)
        otp.finish_delivery(self.db, self.email, self.row().challenge_id, success=True, purpose=reset.PURPOSE)
        self.now += timedelta(seconds=600)
        with self.assertRaises(HTTPException) as caught:
            self.confirm(code)
        self.assertEqual(caught.exception.detail, otp.EXPIRED)

    def test_password_changed_after_issuance_invalidates_code(self):
        _, code = self.issue()
        self.user.password = "changed-outside-this-flow"
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.confirm(code)
        self.assertEqual(caught.exception.detail, otp.EXPIRED)

    def test_expiry_during_hash_is_checked_again(self):
        _, code = self.issue()
        def slow_hash(_password):
            self.now += timedelta(seconds=600)
            return "new-hash"
        with patch.object(reset.pwd_context, "hash", side_effect=slow_hash):
            with self.assertRaises(HTTPException):
                self.confirm(code)
        self.assertIsNone(self.row().consumed_at)
        self.assertEqual(self.db.get(models.User, self.user.id).password, self.old_hash)

    def test_commit_failure_rolls_back_password_and_consumption(self):
        _, code = self.issue()
        original = self.db.commit
        calls = 0
        def fail_final():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated storage failure")
            return original()
        with patch.object(self.db, "commit", side_effect=fail_final):
            with self.assertRaises(HTTPException) as caught:
                self.confirm(code)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(self.db.get(models.User, self.user.id).password, self.old_hash)
        self.assertIsNone(self.row().consumed_at)

    def test_resend_while_hashing_cannot_consume_new_challenge(self):
        _, code = self.issue()
        def resend(_password):
            self.now += timedelta(seconds=61)
            self.issue()
            return "new-hash"
        with patch.object(reset.pwd_context, "hash", side_effect=resend):
            with self.assertRaises(HTTPException) as caught:
                self.confirm(code)
        self.assertEqual(caught.exception.detail, otp.REPLACED)
        self.assertIsNone(self.row().consumed_at)
        self.assertEqual(self.db.get(models.User, self.user.id).password, self.old_hash)

    def test_password_changed_while_hashing_is_not_overwritten(self):
        _, code = self.issue()
        def change_password(_password):
            self.user.password = "password-changed-concurrently"
            self.db.commit()
            return "new-hash"
        with patch.object(reset.pwd_context, "hash", side_effect=change_password):
            with self.assertRaises(HTTPException) as caught:
                self.confirm(code)
        self.assertEqual(caught.exception.detail, otp.EXPIRED)
        self.assertEqual(self.db.get(models.User, self.user.id).password, "password-changed-concurrently")
        self.assertIsNone(self.row().consumed_at)

    def test_pending_guest_cannot_request_or_use_reset_otp_until_approved(self):
        role = models.Role(name="guest")
        self.db.add(role)
        self.db.flush()
        passport = models.UserPassport(user_id=self.user.id, phone="0000000000", is_active=False)
        self.db.add_all([models.UserRole(user_id=self.user.id, role_id=role.id), passport])
        self.db.commit()

        _, code, eligible = reset._reserve(self.db, self.email)
        self.assertFalse(eligible)
        with self.assertRaises(HTTPException):
            otp.finish_delivery(self.db, self.email, self.row().challenge_id,
                                success=False, purpose=reset.PURPOSE)
        with self.assertRaises(HTTPException):
            reset._verify(self.db, self.email, code)
        self.assertEqual(self.user.password, self.old_hash)
        self.assertFalse(passport.is_active)

        passport.is_active = True
        self.db.commit()
        self.now += timedelta(seconds=otp.RESEND_SECONDS)
        _, approved_code = self.issue()
        self.confirm(approved_code)
        self.assertEqual([item.name for item in self.user.roles], ["guest"])
        self.assertTrue(passport.is_active)
        self.assertTrue(pwd_context.verify("New-test-password2!", self.user.password))

    def test_request_endpoint_does_not_send_reset_code_to_pending_guest(self):
        role = models.Role(name="guest")
        self.db.add(role)
        self.db.flush()
        self.db.add_all([models.UserRole(user_id=self.user.id, role_id=role.id),
                         models.UserPassport(user_id=self.user.id, phone="0000000000", is_active=False)])
        self.db.commit()
        mail = AsyncMock()

        with patch.object(reset, "send_otp_mail", mail):
            result = asyncio.run(reset.request_otp(SimpleNamespace(email=self.email), self.db))

        self.assertEqual(result["message"], reset.REQUEST_MESSAGE)
        mail.assert_not_awaited()
        self.assertIsNone(self.row().delivered_at)

    def test_unknown_email_cannot_reset_even_with_internal_code(self):
        _, code, exists = reset._reserve(self.db, "absent@example.com")
        self.assertFalse(exists)
        with self.assertRaises(HTTPException):
            reset._verify(self.db, "absent@example.com", code)

    def test_password_limits_are_validated_before_hashing(self):
        for value in ["short", " " * 8, "x" * 73, "ก" * 25]:
            with self.subTest(value_length=len(value)), self.assertRaises(ValidationError):
                schemas.PasswordReset(email=self.email, otp="123456", new_password=value)

    def test_existing_short_password_can_still_log_in(self):
        self.user.password = pwd_context.hash("short")
        self.db.commit()
        result = auth.login(SimpleNamespace(username=self.email, password="short"), self.db)
        self.assertIn("access_token", result)

    def test_legacy_and_versioned_sessions_are_revoked_after_reset(self):
        tokens = [create_access_token({"sub": self.email}),
                  create_access_token({"sub": self.email, "auth_version": 0})]
        for token in tokens:
            self.assertEqual(users.get_current_user(token, self.db).id, self.user.id)
        _, code = self.issue()
        self.confirm(code)
        for token in tokens:
            with self.assertRaises(HTTPException) as caught:
                users.get_current_user(token, self.db)
            self.assertEqual(caught.exception.status_code, 401)
        latest = create_access_token({"sub": self.email, "auth_version": 1})
        self.assertEqual(users.get_current_user(latest, self.db).id, self.user.id)

    def test_api_request_verify_confirm_login_and_replay(self):
        app = FastAPI()
        app.include_router(reset.router)
        app.include_router(auth.router)
        app.dependency_overrides[reset.get_db] = lambda: self.db
        mail = AsyncMock()
        # Student role avoids changing the existing pending-guest approval rule.
        role = models.Role(name="student")
        self.db.add(role)
        self.db.flush()
        self.db.add(models.UserRole(user_id=self.user.id, role_id=role.id))
        self.db.commit()

        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://unit.test") as client:
                requested = await client.post("/password-reset/request-otp", json={"email": "RESET@example.com"})
                self.assertEqual(requested.status_code, 200)
                code = mail.await_args.args[1]
                self.assertTrue(mail.await_args.kwargs["password_reset"])
                self.assertNotIn(code, requested.text)
                checked = await client.post("/password-reset/verify-otp", json={"email": self.email, "otp": code})
                self.assertEqual(checked.status_code, 200)
                payload = {"email": self.email, "otp": code, "new_password": "New-test-password2!"}
                confirmed = await client.post("/password-reset/confirm", json=payload)
                self.assertEqual(confirmed.status_code, 200)
                replay = await client.post("/password-reset/confirm", json=payload)
                self.assertEqual(replay.status_code, 400)
                old_login = await client.post("/login", data={"username": self.email, "password": "Old-test-password1!"})
                self.assertEqual(old_login.status_code, 401)
                new_login = await client.post("/login", data={"username": self.email, "password": payload["new_password"]})
                self.assertEqual(new_login.status_code, 200)
                unknown = await client.post("/password-reset/request-otp", json={"email": "absent@example.com"})
                self.assertEqual(unknown.json(), requested.json())
                self.assertEqual(mail.await_count, 1)
        with patch.object(reset, "send_otp_mail", mail):
            asyncio.run(flow())

    def test_registration_and_password_reset_share_one_ip_request_budget(self):
        app = FastAPI()
        app.include_router(reset.router)
        app.include_router(auth.router)
        app.dependency_overrides[reset.get_db] = lambda: self.db

        async def flow():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://unit.test",
            ) as client:
                allowed = await client.post(
                    "/password-reset/request-otp", json={"email": self.email},
                )
                blocked = await client.post(
                    "/request-otp", json={"email": "new@example.test"},
                )
                self.assertEqual(allowed.status_code, 200)
                self.assertEqual(blocked.status_code, 429)
                self.assertIn("Retry-After", blocked.headers)
                self.now += timedelta(seconds=otp.IP_RATE_LIMIT_WINDOW_SECONDS)
                allowed_after_window = await client.post(
                    "/password-reset/request-otp", json={"email": self.email},
                )
                self.assertEqual(allowed_after_window.status_code, 200)

        with patch.object(otp, "IP_RATE_LIMIT_MAX_REQUESTS", 1), patch.object(
            reset, "send_otp_mail", AsyncMock(),
        ), patch.object(auth, "send_otp_mail", AsyncMock()):
            asyncio.run(flow())

        row = self.db.query(models.OTPIPRateLimit).one()
        self.assertEqual(row.request_count, 1)
        self.assertEqual(len(row.ip_hash), 64)

    def test_provider_failure_does_not_authorize_or_leak(self):
        with patch.object(reset, "send_otp_mail", AsyncMock(side_effect=RuntimeError("private provider error"))):
            result = asyncio.run(reset.request_otp(SimpleNamespace(email=self.email), self.db))
        self.assertEqual(result["message"], reset.REQUEST_MESSAGE)
        self.assertIsNone(self.row().code_hash)
        self.assertIsNone(self.row().delivered_at)

    def test_table_is_excluded_from_startup_creation(self):
        self.assertTrue(models.PasswordResetOTP.__table__.info["manual_migration"])
        self.assertTrue(models.OTPIPRateLimit.__table__.info["manual_migration"])


if __name__ == "__main__":
    unittest.main()
