import os
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException
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
from routers import blacklist  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class BlacklistTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.admin = models.User(
            first_name="System",
            last_name="Admin",
            email="admin@example.com",
            password="hashed",
        )
        self.rule = models.BlacklistedApp(
            app_name="Notepad",
            description="Initial description",
            match_type="process_name",
            match_value="notepad",
            enabled=True,
        )
        self.other_rule = models.BlacklistedApp(
            app_name="Calculator",
            match_type="process_name",
            match_value="calculator",
            enabled=True,
        )
        self.session.add_all([self.admin, self.rule, self.other_rule])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_website_creation_stores_only_a_normalized_domain(self):
        blacklist.create(
            blacklist.BlacklistCreate(app_name="Example site", match_type="website_domain",
                                      match_value="https://EXAMPLE.com/path?private=1"),
            self.admin, self.session,
        )
        row = self.session.query(models.BlacklistedApp).filter_by(app_name="Example site").one()
        self.assertEqual(row.match_type, "website_domain")
        self.assertEqual(row.match_value, "example.com")

    def test_invalid_website_creation_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            blacklist.create(
                blacklist.BlacklistCreate(app_name="Bad website", match_type="website_domain",
                                          match_value="not a URL"), self.admin, self.session,
            )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIsNone(self.session.query(models.BlacklistedApp).filter_by(app_name="Bad website").first())

    def test_invalid_website_update_does_not_change_existing_program(self):
        with self.assertRaises(HTTPException):
            blacklist.update(self.rule.id,
                             blacklist.BlacklistUpdate(match_type="website_domain", match_value="bad input"),
                             self.admin, self.session)
        self.session.refresh(self.rule)
        self.assertEqual(self.rule.match_type, "process_name")

    def test_update_allows_renaming_without_changing_detection_value(self):
        result = blacklist.update(
            self.rule.id,
            blacklist.BlacklistUpdate(
                app_name="Notepad++",
                description="Updated description",
            ),
            self.admin,
            self.session,
        )

        self.session.refresh(self.rule)
        self.assertEqual(result["message"], "Blacklist rule updated.")
        self.assertEqual(self.rule.app_name, "Notepad++")
        self.assertEqual(self.rule.description, "Updated description")
        self.assertEqual(self.rule.match_value, "notepad")

    def test_update_rejects_a_duplicate_name(self):
        with self.assertRaises(HTTPException) as context:
            blacklist.update(
                self.rule.id,
                blacklist.BlacklistUpdate(app_name=" calculator "),
                self.admin,
                self.session,
            )

        self.assertEqual(context.exception.status_code, 400)
        self.session.refresh(self.rule)
        self.assertEqual(self.rule.app_name, "Notepad")

    def test_update_rejects_an_empty_name(self):
        with self.assertRaises(HTTPException) as context:
            blacklist.update(
                self.rule.id,
                blacklist.BlacklistUpdate(app_name="   "),
                self.admin,
                self.session,
            )

        self.assertEqual(context.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
