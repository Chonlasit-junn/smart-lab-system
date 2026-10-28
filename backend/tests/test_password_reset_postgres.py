"""Opt-in concurrency/migration tests, only in a disposable local test database.

Never reads SQLALCHEMY_DATABASE_URL or the application's environment files.
"""
import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"
import models
import otp_service as otp
import schemas
from routers import password_reset as reset

TEST_URL = os.getenv("SMART_LAB_TEST_POSTGRES_URL")


@unittest.skipUnless(TEST_URL, "Opt-in local PostgreSQL URL is not configured")
class PasswordResetPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(TEST_URL)
        if (url.get_backend_name() != "postgresql" or url.host not in {"127.0.0.1", "localhost", "::1"}
                or not (url.database or "").startswith("smartlab_test") or url.query):
            raise RuntimeError("Only an explicit disposable loopback smartlab_test database is allowed")
        cls.schema = "otp_reset_test_" + uuid4().hex
        cls.raw = create_engine(url, hide_parameters=True, connect_args={
            "connect_timeout": 5, "options": "-c lock_timeout=5000 -c statement_timeout=10000",
        })
        cls.engine = cls.raw.execution_options(schema_translate_map={None: cls.schema})
        with cls.raw.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{cls.schema}"')
        # Cleanup is registered even if migration setup fails, and touches only
        # this test's locally generated schema in the guarded test database.
        cls.addClassCleanup(cls.cleanup)
        models.User.__table__.create(cls.engine)
        for model in (models.Role, models.UserRole, models.Student, models.UserPassport):
            model.__table__.create(cls.engine)
        migration = (Path(__file__).resolve().parents[1] / "migrations/015_password_reset_otp.sql").read_text(encoding="utf-8")
        ip_migration = (Path(__file__).resolve().parents[1] / "migrations/016_otp_ip_rate_limit.sql").read_text(encoding="utf-8")
        with cls.raw.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(migration.replace("public.", f'"{cls.schema}".'))
            connection.exec_driver_sql(ip_migration.replace("public.", f'"{cls.schema}".'))
        cls.sessions = sessionmaker(bind=cls.engine, autoflush=False)

    @classmethod
    def cleanup(cls):
        with cls.raw.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{cls.schema}" CASCADE')
        cls.raw.dispose()

    def setUp(self):
        self.email = uuid4().hex + "@example.test"
        self.db = self.sessions()
        self.addCleanup(self.db.close)
        user = models.User(email=self.email, first_name="Test", last_name="Recovery", password="old-synthetic-hash")
        self.db.add(user)
        self.db.flush()
        self.db.add(models.UserPassport(user_id=user.id, is_active=True))
        self.db.commit()
        for patcher in [patch.dict(os.environ, {"OTP_SECRET_KEY": "local-postgres-test-secret-01234567890123"}),
                        patch.object(otp, "utc_now", return_value=datetime(2026, 10, 22, tzinfo=timezone.utc))]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def parallel(self, count, action):
        barrier = threading.Barrier(count)
        def worker(_index):
            with self.sessions() as db:
                barrier.wait(timeout=10)
                try:
                    action(db)
                    return "ok"
                except HTTPException as error:
                    return error.status_code
        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(worker, range(count)))

    def issue(self):
        challenge, code, _ = reset._reserve(self.db, self.email)
        otp.finish_delivery(self.db, self.email, challenge, success=True, purpose=reset.PURPOSE)
        return code

    def test_concurrent_first_request_has_one_winner(self):
        self.assertCountEqual(self.parallel(2, lambda db: reset._reserve(db, self.email)), ["ok", 429])

    def test_concurrent_wrong_attempts_are_not_lost(self):
        self.issue()
        results = self.parallel(5, lambda db: reset._verify(db, self.email, "xxxxxx"))
        self.assertCountEqual(results, [400, 400, 400, 400, 429])
        self.assertEqual(self.db.get(models.PasswordResetOTP, self.email).window_attempts, 5)

    def test_concurrent_confirm_changes_password_once(self):
        code = self.issue()
        request = schemas.PasswordReset(email=self.email, otp=code, new_password="Synthetic-new-password1!")
        self.assertCountEqual(self.parallel(2, lambda db: reset.confirm(request, db)), ["ok", 400])
        user = self.db.query(models.User).filter_by(email=self.email).one()
        self.assertEqual(user.auth_version, 1)

    def test_actual_migration_rls_checks_and_auth_version(self):
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT c.relrowsecurity, (SELECT count(*) FROM pg_constraint WHERE conrelid=c.oid) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=:schema AND c.relname='password_reset_otps'"
            ), {"schema": self.schema}).one()
            self.assertTrue(row[0])
            self.assertEqual(row[1], 4)  # PK, two checks, account FK.
        self.assertEqual(self.db.query(models.User).filter_by(email=self.email).one().auth_version, 0)
