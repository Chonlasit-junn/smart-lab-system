import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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
from device_registry import hash_device_token  # noqa: E402
from routers import gatekeeper  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


class GatekeeperRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.lab = models.Lab(name="Camera Lab", code="CAMERA-LAB", capacity=20, status="active")
        self.other_lab = models.Lab(name="Other Lab", code="OTHER-LAB", capacity=20, status="active")
        self.session.add_all([self.lab, self.other_lab])
        self.session.flush()
        self.gatekeeper_device = models.LabDevice(
            device_id="gatekeeper-camera-001",
            lab_id=self.lab.id,
            device_name="Entrance Camera",
            status="active",
            agent_token_hash=hash_device_token("gatekeeper-secret"),
            agent_version="gatekeeper",
        )
        self.agent_device = models.LabDevice(
            device_id="agent-workstation-001",
            lab_id=self.lab.id,
            device_name="Agent workstation",
            status="active",
            agent_token_hash=hash_device_token("agent-secret"),
            agent_version="source",
        )
        self.session.add_all([self.gatekeeper_device, self.agent_device])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_registered_gatekeeper_uses_assigned_lab_not_client_lab_code(self):
        lab = gatekeeper.resolve_gatekeeper_lab(
            self.session,
            device_id="gatekeeper-camera-001",
            device_token="gatekeeper-secret",
            lab_code="OTHER-LAB",
            gatekeeper_key=None,
        )

        self.assertEqual(lab.id, self.lab.id)

    def test_agent_device_credential_cannot_authenticate_as_gatekeeper(self):
        with self.assertRaises(HTTPException) as context:
            gatekeeper.resolve_gatekeeper_lab(
                self.session,
                device_id="agent-workstation-001",
                device_token="agent-secret",
                lab_code=self.lab.code,
                gatekeeper_key=None,
            )

        self.assertEqual(context.exception.status_code, 403)

    def test_unregistered_camera_requires_legacy_key_or_device_registration(self):
        with patch.object(gatekeeper, "GATEKEEPER_API_KEY", None):
            with self.assertRaises(HTTPException) as context:
                gatekeeper.resolve_gatekeeper_lab(
                    self.session,
                    device_id=None,
                    device_token=None,
                    lab_code=self.lab.code,
                    gatekeeper_key=None,
                )
        self.assertEqual(context.exception.status_code, 401)

    def test_legacy_key_path_remains_available_when_configured(self):
        with patch.object(gatekeeper, "GATEKEEPER_API_KEY", "legacy-secret"):
            lab = gatekeeper.resolve_gatekeeper_lab(
                self.session,
                device_id=None,
                device_token=None,
                lab_code=self.lab.code,
                gatekeeper_key="legacy-secret",
            )

        self.assertEqual(lab.id, self.lab.id)


if __name__ == "__main__":
    unittest.main()
