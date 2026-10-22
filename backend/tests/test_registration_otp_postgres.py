"""Opt-in local PostgreSQL checks; NEVER reads the application's database URL.

Requires SMART_LAB_TEST_POSTGRES_URL pointing to a disposable loopback database
whose name starts with smartlab_test. Only a fresh, uniquely named test schema
is created/removed. No production schema or user_otps data is touched.
"""

import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import models  # noqa: E402
import otp_service as otp  # noqa: E402


TEST_URL = os.getenv("SMART_LAB_TEST_POSTGRES_URL")


@unittest.skipUnless(TEST_URL, "Opt-in local PostgreSQL URL is not configured")
class RegistrationOTPPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(TEST_URL)
        if (
            url.get_backend_name() != "postgresql"
            or url.host not in {"localhost", "127.0.0.1", "::1"}
            or not (url.database or "").startswith("smartlab_test")
            or url.query
        ):
            raise RuntimeError("Only an explicit disposable loopback smartlab_test database is allowed")
        cls.schema = "otp_test_" + uuid4().hex
        cls.raw_engine = create_engine(
            url, hide_parameters=True,
            connect_args={"connect_timeout": 5, "options": "-c lock_timeout=5000 -c statement_timeout=10000"},
        )
        # The identifier is generated locally, not from user/database input.
        with cls.raw_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{cls.schema}"')
            migration = (BACKEND_DIR / "migrations/014_registration_otp_security.sql").read_text(encoding="utf-8")
            connection.exec_driver_sql(migration.replace("public.registration_otps", f'"{cls.schema}".registration_otps'))
        cls.engine = cls.raw_engine.execution_options(schema_translate_map={None: cls.schema})
        cls.sessions = sessionmaker(bind=cls.engine, autoflush=False)

    @classmethod
    def tearDownClass(cls):
        with cls.raw_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{cls.schema}" CASCADE')
        cls.raw_engine.dispose()

    def setUp(self):
        self.db = self.sessions()
        self.db.query(models.RegistrationOTP).delete()
        self.db.commit()
        self.now = datetime(2026, 10, 22, 14, tzinfo=timezone.utc)
        self.clock = patch.object(otp, "utc_now", side_effect=lambda: self.now)
        self.key = patch.dict(os.environ, {"OTP_SECRET_KEY": "local-postgres-test-only-key-0123456789"})
        self.clock.start()
        self.key.start()
        self.email = "local@example.test"

    def tearDown(self):
        self.db.close()
        self.key.stop()
        self.clock.stop()

    def issue(self):
        challenge, code = otp.reserve_otp(self.db, self.email)
        otp.finish_delivery(self.db, self.email, challenge, success=True)
        return challenge, code

    def parallel(self, count, operation):
        barrier = threading.Barrier(count)

        def worker(_index):
            with self.sessions() as db:
                barrier.wait(timeout=10)
                try:
                    operation(db)
                    db.commit()
                    return "ok"
                except HTTPException as error:
                    return error.status_code

        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(worker, range(count)))

    def test_concurrent_first_issuance_reserves_only_once(self):
        results = self.parallel(2, lambda db: otp.reserve_otp(db, self.email))
        self.assertCountEqual(results, ["ok", 429])
        self.assertEqual(self.db.query(models.RegistrationOTP).count(), 1)

    def test_concurrent_guesses_do_not_lose_attempt_counts(self):
        self.issue()
        results = self.parallel(5, lambda db: otp.verify_otp(db, self.email, "xxxxxx"))
        self.assertCountEqual(results, [400, 400, 400, 400, 429])
        row = self.db.get(models.RegistrationOTP, self.email, populate_existing=True)
        self.assertEqual((row.failed_attempts, row.window_attempts), (5, 5))

    def test_concurrent_consumption_succeeds_only_once(self):
        challenge, code = self.issue()
        results = self.parallel(2, lambda db: otp.verify_otp(
            db, self.email, code, consume=True, expected_challenge_id=challenge,
        ))
        self.assertCountEqual(results, ["ok", 400])

    def test_cached_session_cannot_accept_replaced_issuance(self):
        challenge, code = self.issue()
        with self.sessions(expire_on_commit=False) as stale:
            old = stale.get(models.RegistrationOTP, self.email)
            stale.commit()
            self.now += timedelta(seconds=60)
            replacement, _ = self.issue()
            self.assertEqual(old.challenge_id, challenge)
            with self.assertRaises(HTTPException) as error:
                otp.verify_otp(stale, self.email, code, consume=True, expected_challenge_id=challenge)
            self.assertEqual(error.exception.detail, otp.REPLACED)
            self.assertNotEqual(replacement, challenge)

    def test_actual_migration_has_rls_and_enforced_checks(self):
        with self.engine.connect() as connection:
            rls = connection.execute(text(
                "SELECT relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=:schema AND c.relname='registration_otps'"
            ), {"schema": self.schema}).scalar_one()
            self.assertTrue(rls)
        self.db.add(models.RegistrationOTP(email="UPPER@example.test"))
        with self.assertRaises(IntegrityError):
            self.db.flush()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
