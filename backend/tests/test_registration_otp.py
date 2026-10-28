import asyncio
import io
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI, HTTPException, UploadFile
import httpx
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR)) if str(BACKEND_DIR) not in sys.path else None
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import models  # noqa: E402
import otp_service as otp  # noqa: E402
from database import Base  # noqa: E402
from routers import auth  # noqa: E402
import utils  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class RegistrationOTPTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.now = datetime(2026, 10, 22, 14, tzinfo=timezone.utc)
        self.clock = patch.object(otp, "utc_now", side_effect=lambda: self.now)
        self.clock.start()
        self.key = patch.dict(os.environ, {"OTP_SECRET_KEY": "unit-test-only-secret-key-0123456789"})
        self.key.start()
        self.email = "new@example.com"
        self.temp = tempfile.TemporaryDirectory(dir=BACKEND_DIR / "runtime")
        self.uploads = patch.object(auth, "UPLOAD_DIR", self.temp.name)
        self.uploads.start()
        self.storage = patch.object(auth, "uses_supabase_storage", return_value=False)
        self.storage.start()
        self.face = patch.object(auth, "get_deepface", return_value=SimpleNamespace(
            represent=Mock(return_value=[{"embedding": [0.1, 0.2]}]),
        ))
        self.face.start()
        self.hashing = patch.object(auth.pwd_context, "hash", return_value="test-password-hash")
        self.hashing.start()
        self.db.add_all([models.Role(name="student"), models.Role(name="guest")])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        for patcher in (self.hashing, self.face, self.storage, self.uploads, self.key, self.clock):
            patcher.stop()
        self.temp.cleanup()

    def issue(self, email=None):
        email = email or self.email
        challenge, code = otp.reserve_otp(self.db, email)
        timing = otp.finish_delivery(self.db, email, challenge, success=True)
        self.assertEqual(timing["expires_in_seconds"], 600)
        return challenge, code

    def row(self, email=None):
        return self.db.get(models.RegistrationOTP, email or self.email, populate_existing=True)

    def register(self, code, email=None, password="test-pass", image_size=(10, 10)):
        image = io.BytesIO()
        Image.new("RGB", image_size).save(image, format="JPEG")
        return asyncio.run(auth.register(
            email=email or self.email, otp=code, password=password,
            first_name="Test", last_name="Account", student_id="S001",
            faculty="Science", department="Computing", phone="0000000000",
            face_image=UploadFile(filename="face.jpg", file=io.BytesIO(image.getvalue())),
            db=self.db,
        ))

    def test_multiple_faces_do_not_create_account_or_consume_otp_or_keep_image(self):
        _, code = self.issue()
        model = auth.get_deepface.return_value
        model.represent.return_value = [{"embedding": [.1, .2]}, {"embedding": [.2, .1]}]
        with self.assertRaises(HTTPException) as caught:
            self.register(code)
        self.assertEqual(caught.exception.detail, "Exactly one face is required.")
        self.assertEqual(self.db.query(models.User).count(), 0)
        self.assertIsNone(self.row().consumed_at)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        model.represent.return_value = [{"embedding": [.1, .2]}]
        self.register(code)
        self.assertEqual(self.db.query(models.User).count(), 1)

    def test_busy_shared_gatekeeper_slot_preserves_otp_and_creates_no_files(self):
        from face_service import gatekeeper_inference_slot
        _, code = self.issue()
        with gatekeeper_inference_slot(), self.assertRaises(HTTPException) as caught:
            self.register(code)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.headers["Retry-After"], "1")
        self.assertIsNone(self.row().consumed_at)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        auth.get_deepface.assert_not_called()
        self.register(code)
        self.assertIsNotNone(self.row().consumed_at)

    def test_face_worker_releases_db_and_does_not_block_another_http_request(self):
        _, code = self.issue()
        started = threading.Event()
        release = threading.Event()
        main_thread = threading.get_ident()
        observed = {}

        def represent(**_kwargs):
            observed["thread"] = threading.get_ident()
            observed["transaction"] = self.db.in_transaction()
            started.set()
            observed["released"] = release.wait(3)
            return [{"embedding": [.1, .2]}]

        auth.get_deepface.return_value.represent.side_effect = represent
        app = FastAPI()
        app.include_router(auth.router)
        app.dependency_overrides[auth.get_db] = lambda: self.db

        @app.get("/probe")
        async def probe():
            return {"ok": True}

        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://unit.test") as client:
                image = io.BytesIO()
                Image.new("RGB", (100, 100)).save(image, "JPEG")
                task = asyncio.create_task(client.post("/register", data={
                    "email": self.email, "otp": code, "password": "test-password", "first_name": "Test",
                    "last_name": "Worker", "phone": "0812345678",
                }, files={"face_image": ("face.jpg", image.getvalue(), "image/jpeg")}))
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 2))
                    self.assertFalse(task.done())
                    result = await asyncio.wait_for(client.get("/probe"), timeout=.5)
                    self.assertEqual(result.json(), {"ok": True})
                finally:
                    release.set()
                result = await task
                self.assertEqual(result.status_code, 200, result.text)

        asyncio.run(flow())
        self.assertNotEqual(observed["thread"], main_thread)
        self.assertFalse(observed["transaction"])
        self.assertTrue(observed["released"])

    def test_ai_exception_cleans_temp_file_and_can_retry_same_otp(self):
        _, code = self.issue()
        paths = []

        def unavailable(img_path, **_kwargs):
            paths.append(Path(img_path))
            self.assertTrue(paths[-1].exists())
            raise RuntimeError("private model details")

        auth.get_deepface.return_value.represent.side_effect = unavailable
        with self.assertRaises(HTTPException) as caught:
            self.register(code)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("private model", caught.exception.detail)
        self.assertFalse(paths[0].exists())
        self.assertIsNone(self.row().consumed_at)
        self.assertEqual(self.db.query(models.User).count(), 0)
        auth.get_deepface.return_value.represent.side_effect = None
        self.register(code)

    def test_no_face_and_tiny_face_are_rejected_without_consuming_otp(self):
        _, code = self.issue()
        for faces in ([], [{"embedding": [.1, .2], "facial_area": {"w": 20, "h": 20}}]):
            auth.get_deepface.return_value.represent.return_value = faces
            with self.assertRaises(HTTPException):
                self.register(code)
            self.assertIsNone(self.row().consumed_at)
            self.assertEqual(self.db.query(models.User).count(), 0)
            self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_embedding_uses_larger_image_but_saved_avatar_stays_small(self):
        from face_service import FACE_REPRESENT_OPTIONS
        _, code = self.issue()
        def represent(img_path, **options):
            with Image.open(img_path) as image:
                self.assertEqual(image.size, (1024, 768))
            self.assertEqual(options, FACE_REPRESENT_OPTIONS)
            return [{"embedding": [.1, .2]}]
        auth.get_deepface.return_value.represent.side_effect = represent
        self.register(code, image_size=(1600, 1200))
        saved = list(Path(self.temp.name).glob('*.jpg'))
        self.assertEqual(len(saved), 1)
        with Image.open(saved[0]) as image:
            self.assertEqual(image.size, (200, 150))

    def test_invalid_registration_password_does_not_spend_otp_or_process_face(self):
        _, code = self.issue()
        for password in ["short", " " * 8, "x" * 73, "ก" * 25, "😀" * 4]:
            with self.subTest(length=len(password)), self.assertRaises(HTTPException) as caught:
                self.register(code, password=password)
            self.assertEqual(caught.exception.status_code, 422)
            self.assertIsNone(self.row().consumed_at)
        auth.pwd_context.hash.assert_not_called()
        auth.get_deepface.assert_not_called()
        self.assertEqual(self.db.query(models.User).count(), 0)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        self.register(code, password="valid-new-password")

    def test_valid_multibyte_password_is_not_trimmed_or_truncated(self):
        for index, password in enumerate(["x" * 72, "ก" * 24, "😀" * 8, " padded password "]):
            email = f"password{index}@example.com"
            _, code = self.issue(email)
            self.register(code, email=email, password=password)
            auth.pwd_context.hash.assert_called_with(password)

    def test_multipart_password_validation_cannot_be_bypassed_by_client(self):
        app = FastAPI()
        app.include_router(auth.router)
        app.dependency_overrides[auth.get_db] = lambda: self.db
        _, code = self.issue()
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://unit.test") as client:
                result = await client.post("/register", data={"email": self.email, "otp": code,
                    "password": "short", "first_name": "Test", "last_name": "Policy"},
                    files={"face_image": ("invalid.jpg", b"not-an-image", "image/jpeg")})
                self.assertEqual(result.status_code, 422)
                self.assertEqual(result.json()["detail"], "Password must be 8 or more characters and at most 72 UTF-8 bytes.")
        asyncio.run(flow())
        self.assertIsNone(self.row().consumed_at)
        auth.get_deepface.assert_not_called()

    def test_issue_hash_only_and_repeat_verify_does_not_consume(self):
        challenge, code = self.issue()
        self.assertEqual(len(code), 6)
        self.assertEqual(len(self.row().code_hash), 64)
        self.assertNotEqual(self.row().code_hash, code)
        for _ in range(2):
            self.assertEqual(otp.verify_otp(self.db, self.email, code), challenge)
        self.assertIsNone(self.row().consumed_at)

    def test_verify_then_register_guest_and_prevent_replay(self):
        _, code = self.issue()
        auth.verify_otp(SimpleNamespace(email=" NEW@EXAMPLE.COM ", otp=code), self.db)
        self.assertIn("successful", self.register(code)["message"])
        user = self.db.query(models.User).filter_by(email=self.email).one()
        self.assertFalse(self.db.query(models.UserPassport).filter_by(user_id=user.id).one().is_active)
        self.assertEqual(self.db.get(models.UserPoints, user.id).points, 100)
        self.assertEqual(user.roles[0].name, "guest")
        with self.assertRaises(HTTPException) as error:
            otp.verify_otp(self.db, self.email, code)
        self.assertEqual(error.exception.detail, otp.EXPIRED)

    def test_direct_registration_student_preserves_profile_and_role(self):
        email = "new@bumail.net"
        _, code = self.issue(email)
        self.register(code, email)
        user = self.db.query(models.User).filter_by(email=email).one()
        self.assertEqual(user.roles[0].name, "student")
        self.assertEqual(self.db.query(models.Student).filter_by(user_id=user.id).one().faculty, "Science")

    def test_exact_expiration_and_expiry_after_verify(self):
        _, code = self.issue()
        otp.verify_otp(self.db, self.email, code)
        self.now += timedelta(seconds=600)
        with self.assertRaises(HTTPException) as error:
            self.register(code)
        self.assertEqual(error.exception.detail, otp.EXPIRED)
        self.assertEqual(self.db.query(models.User).count(), 0)

    def test_legacy_plaintext_code_is_never_accepted(self):
        self.db.add(models.UserOTP(email=self.email, otp_code="123456"))
        self.db.commit()
        with self.assertRaises(HTTPException):
            otp.verify_otp(self.db, self.email, "123456")
        self.assertEqual(self.db.query(models.UserOTP).count(), 1)

    def test_shared_wrong_attempt_budget_and_lock(self):
        _, code = self.issue()
        wrong = "999999" if code != "999999" else "888888"
        for attempt in range(5):
            with self.assertRaises(HTTPException) as error:
                if attempt % 2:
                    self.register(wrong)
                else:
                    auth.verify_otp(SimpleNamespace(email=self.email, otp=wrong), self.db)
            self.assertEqual(error.exception.status_code, 429 if attempt == 4 else 400)
            self.assertEqual(self.row().failed_attempts, attempt + 1)
        with self.assertRaises(HTTPException) as error:
            otp.verify_otp(self.db, self.email, code)
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "600")

    def test_cooldown_is_server_side(self):
        self.issue()
        self.now += timedelta(seconds=59)
        with self.assertRaises(HTTPException) as error:
            otp.reserve_otp(self.db, self.email)
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "1")
        self.now += timedelta(seconds=1)
        self.issue()

    def test_resend_replaces_code_but_does_not_reset_guessing_window(self):
        first, code = self.issue()
        with self.assertRaises(HTTPException):
            otp.verify_otp(self.db, self.email, "x" * 6)
        self.now += timedelta(seconds=60)
        second, new_code = self.issue()
        self.assertNotEqual(first, second)
        self.assertEqual(self.row().window_attempts, 1)
        with self.assertRaises(HTTPException):
            otp.verify_otp(self.db, self.email, code, expected_challenge_id=first)
        otp.verify_otp(self.db, self.email, new_code)

    def test_lock_cannot_be_cleared_by_requesting_new_code(self):
        _, code = self.issue()
        for _ in range(5):
            with self.assertRaises(HTTPException):
                otp.verify_otp(self.db, self.email, "x" * 6)
        self.now += timedelta(seconds=60)
        with self.assertRaises(HTTPException) as error:
            otp.reserve_otp(self.db, self.email)
        self.assertEqual(error.exception.detail, otp.EXHAUSTED)
        self.now += timedelta(seconds=540)
        _, new_code = self.issue()
        self.assertEqual(self.row().window_attempts, 0)
        otp.verify_otp(self.db, self.email, new_code)

    def test_pending_or_failed_mail_cannot_authorize_and_keeps_cooldown(self):
        challenge, code = otp.reserve_otp(self.db, self.email)
        with self.assertRaises(HTTPException):
            otp.verify_otp(self.db, self.email, code)
        with self.assertRaises(HTTPException) as error:
            otp.finish_delivery(self.db, self.email, challenge, success=False)
        self.assertEqual(error.exception.status_code, 503)
        self.assertIsNone(self.row().code_hash)
        with self.assertRaises(HTTPException):
            otp.reserve_otp(self.db, self.email)

    def test_late_mail_completion_does_not_clobber_newer_issuance(self):
        first, _ = otp.reserve_otp(self.db, self.email)
        self.now += timedelta(seconds=60)
        second, _ = self.issue()
        for success in (True, False):
            with self.assertRaises(HTTPException) as error:
                otp.finish_delivery(self.db, self.email, first, success=success)
            self.assertEqual(error.exception.detail, otp.REPLACED)
            self.assertEqual(self.row().challenge_id, second)
            self.assertIsNotNone(self.row().code_hash)

    def test_resend_during_face_processing_rejects_and_rolls_back_account(self):
        _, code = self.issue()

        def replace(**_kwargs):
            self.now += timedelta(seconds=60)
            self.issue()
            return [{"embedding": [0.1]}]

        with patch.object(auth, "get_deepface", return_value=SimpleNamespace(represent=replace)):
            with self.assertRaises(HTTPException) as error:
                self.register(code)
        self.assertEqual(error.exception.detail, otp.REPLACED)
        self.assertEqual(self.db.query(models.User).count(), 0)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_expiry_during_face_processing_rejects_and_rolls_back_account(self):
        _, code = self.issue()

        def expire(**_kwargs):
            self.now += timedelta(seconds=600)
            return [{"embedding": [0.1]}]

        with patch.object(auth, "get_deepface", return_value=SimpleNamespace(represent=expire)):
            with self.assertRaises(HTTPException) as error:
                self.register(code)
        self.assertEqual(error.exception.detail, otp.EXPIRED)
        self.assertEqual(self.db.query(models.User).count(), 0)

    def test_face_failure_preserves_valid_otp(self):
        _, code = self.issue()
        with patch.object(auth, "get_deepface", side_effect=ValueError("no face")):
            with self.assertRaises(HTTPException):
                self.register(code)
        otp.verify_otp(self.db, self.email, code)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_commit_failure_rolls_back_consumption_and_removes_image(self):
        _, code = self.issue()
        commit = self.db.commit
        calls = 0

        def fail_final_commit():
            nonlocal calls
            calls += 1
            if calls == 2:  # Preflight commits first, account creation second.
                raise RuntimeError("simulated commit failure")
            return commit()

        with patch.object(self.db, "commit", side_effect=fail_final_commit):
            with self.assertRaises(HTTPException) as error:
                self.register(code)
        self.assertEqual(error.exception.status_code, 500)
        self.assertEqual(self.db.query(models.User).count(), 0)
        self.assertIsNone(self.row().consumed_at)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        otp.verify_otp(self.db, self.email, code)

    def test_request_endpoint_normalization_timing_and_sanitized_mail_error(self):
        mail = AsyncMock()
        with patch.object(auth, "send_otp_mail", mail):
            result = asyncio.run(auth.request_otp(SimpleNamespace(email=" NEW@EXAMPLE.COM "), self.db))
        self.assertEqual(result["account_type"], "general")
        self.assertEqual(result["retry_after_seconds"], 60)
        self.assertEqual(mail.call_args.args[0], self.email)
        self.now += timedelta(seconds=60)
        with patch.object(auth, "send_otp_mail", AsyncMock(side_effect=RuntimeError("private provider response"))):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(auth.request_otp(SimpleNamespace(email=self.email), self.db))
        self.assertEqual(error.exception.detail, otp.UNAVAILABLE)
        self.assertNotIn("private", error.exception.detail)

    def test_missing_secret_fails_closed_without_challenge(self):
        with patch.dict(os.environ, {"OTP_SECRET_KEY": "", "SECRET_KEY": ""}):
            with self.assertRaises(HTTPException) as error:
                otp.reserve_otp(self.db, self.email)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.db.query(models.RegistrationOTP).count(), 0)

    def test_alternate_digit_encoding_is_not_accepted(self):
        _, code = self.issue()
        fullwidth = "".join(chr(ord(character) + 0xFEE0) for character in code)
        with self.assertRaises(HTTPException) as error:
            otp.verify_otp(self.db, self.email, fullwidth)
        self.assertEqual(error.exception.detail, otp.INVALID)
        self.assertEqual(self.row().failed_attempts, 1)

    def test_failed_final_check_never_commits_pending_account_rows(self):
        challenge, code = self.issue()
        self.db.add(models.User(email=self.email, password="hash", first_name="Test", last_name="Pending"))
        self.db.flush()
        with self.assertRaises(HTTPException):
            otp.verify_otp(self.db, self.email, "xxxxxx", consume=True, expected_challenge_id=challenge)
        self.assertEqual(self.db.query(models.User).count(), 0)
        self.assertIsNone(self.row().consumed_at)
        otp.verify_otp(self.db, self.email, code)

    def test_storage_failure_preserves_valid_otp(self):
        _, code = self.issue()
        temporary_file = auth.NamedTemporaryFile
        with (
            patch.object(auth, "uses_supabase_storage", return_value=True),
            patch.object(auth, "NamedTemporaryFile", side_effect=lambda **kwargs: temporary_file(dir=self.temp.name, **kwargs)),
            patch.object(auth, "upload_profile_image", AsyncMock(side_effect=auth.ProfileStorageError("test failure"))),
            patch.object(auth, "delete_profile_image", AsyncMock()),
        ):
            with self.assertRaises(HTTPException) as error:
                self.register(code)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.db.query(models.User).count(), 0)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        otp.verify_otp(self.db, self.email, code)

    def test_missing_mail_configuration_does_not_claim_delivery(self):
        with patch.object(utils, "BREVO_API_KEY", None):
            with self.assertRaises(RuntimeError):
                asyncio.run(utils.send_otp_mail(self.email, "123456"))

    def test_table_requires_manual_migration(self):
        self.assertTrue(models.RegistrationOTP.__table__.info["manual_migration"])

    def test_json_verify_then_multipart_registration_api_contract(self):
        app = FastAPI()
        app.include_router(auth.router)
        app.dependency_overrides[auth.get_db] = lambda: self.db
        mail = AsyncMock()

        async def flow():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://unit.test",
            ) as client:
                issued = await client.post("/request-otp", json={"email": self.email})
                self.assertEqual(issued.status_code, 200)
                self.assertEqual(issued.json()["account_type"], "general")
                self.assertNotIn("code", issued.json())
                code = mail.await_args.args[1]
                rejected = await client.post("/verify-otp", json={"email": self.email, "otp": "xxxxxx"})
                self.assertEqual(rejected.status_code, 400)
                self.assertIsInstance(rejected.json()["detail"], str)
                verified = await client.post("/verify-otp", json={"email": self.email, "otp": code})
                self.assertEqual(verified.status_code, 200)
                image = io.BytesIO()
                Image.new("RGB", (10, 10)).save(image, format="JPEG")
                registered = await client.post(
                    "/register",
                    data={"email": self.email, "otp": code, "password": "synthetic",
                          "first_name": "API", "last_name": "Test", "phone": "0000000000"},
                    files={"face_image": ("face.jpg", image.getvalue(), "image/jpeg")},
                )
                self.assertEqual(registered.status_code, 200)
                replay = await client.post("/verify-otp", json={"email": self.email, "otp": code})
                self.assertEqual(replay.status_code, 400)

        with patch.object(auth, "send_otp_mail", mail):
            asyncio.run(flow())


if __name__ == "__main__":
    unittest.main()
