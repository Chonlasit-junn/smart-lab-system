import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import models  # noqa: E402
from database import Base  # noqa: E402
from routers import auth  # noqa: E402
from utils import normalize_email  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class AuthEmailNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.password = "Test@1234"
        self.user = models.User(
            first_name="Case",
            last_name="Insensitive",
            email="User@Example.com",
            password=auth.pwd_context.hash(self.password),
        )
        self.session.add(self.user)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_normalize_email_trims_and_casefolds(self):
        self.assertEqual(
            normalize_email("  USER@EXAMPLE.COM "),
            "user@example.com",
        )

    def test_login_accepts_different_email_casing(self):
        result = auth.login(
            SimpleNamespace(
                username=" USER@EXAMPLE.COM ",
                password=self.password,
            ),
            self.session,
        )

        self.assertEqual(result["token_type"], "bearer")
        self.assertTrue(result["access_token"])


if __name__ == "__main__":
    unittest.main()
