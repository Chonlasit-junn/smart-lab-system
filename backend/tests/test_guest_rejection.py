"""Guest approval/rejection regression tests, never an application database."""
import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"
import models
from database import Base, get_db
from routers import admin, users


@compiles(JSONB, 'sqlite')
def compile_jsonb(_type, _compiler, **_kwargs):
    return 'TEXT'


class GuestRejectionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        @event.listens_for(self.engine, 'connect')
        def enable_fk(connection, _record):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.actor = models.User(email='admin@example.test', first_name='Test', last_name='Admin', password='synthetic')
        self.guest = models.User(email='pending@example.test', first_name='Test', last_name='Guest', password='synthetic', profile_pic='profiles/test/avatar.jpg')
        guest_role, admin_role = models.Role(name='guest'), models.Role(name='admin')
        self.db.add_all([self.actor, self.guest, guest_role, admin_role])
        self.db.flush()
        self.guest_id = self.guest.id
        self.guest.roles = [guest_role]
        self.actor.roles = [admin_role]
        self.db.add_all([models.UserPassport(user_id=self.guest.id, is_active=False),
                         models.UserPoints(user_id=self.guest.id, points=100),
                         models.UserPoints(user_id=self.actor.id, points=100),
                         models.PasswordResetOTP(email=self.guest.email, user_id=self.guest.id)])
        self.db.commit()
        self.cleanup = patch.object(admin, 'delete_profile_image_sync')
        self.image_delete = self.cleanup.start()
        self.addCleanup(self.cleanup.stop)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def verify(self, action='reject'):
        return admin.verify_user(self.guest_id, admin.VerifyAction(action=action), self.actor, self.db)

    def assert_intact(self):
        self.assertIsNotNone(self.db.get(models.User, self.guest_id))
        self.assertEqual(self.db.get(models.UserPoints, self.guest_id).points, 100)
        self.assertFalse(self.db.query(models.UserPassport).filter_by(user_id=self.guest_id).one().is_active)
        self.image_delete.assert_not_called()

    def test_reject_removes_initial_rows_and_only_then_cleans_image(self):
        # Force the problematic backref into the identity map before deletion.
        self.assertEqual(len(self.guest.points_record), 1)
        self.verify()
        self.assertIsNone(self.db.get(models.User, self.guest_id))
        self.assertIsNone(self.db.get(models.UserPoints, self.guest_id))
        self.assertEqual(self.db.query(models.UserPassport).count(), 0)
        self.assertEqual(self.db.query(models.UserRole).filter_by(user_id=self.guest_id).count(), 0)
        self.assertEqual(self.db.query(models.PasswordResetOTP).count(), 0)
        self.assertEqual(self.db.get(models.UserPoints, self.actor.id).points, 100)
        self.image_delete.assert_called_once_with('profiles/test/avatar.jpg')

    def test_legacy_guest_without_points_can_be_rejected(self):
        self.db.delete(self.db.get(models.UserPoints, self.guest_id))
        self.db.commit()
        self.verify()
        self.assertIsNone(self.db.get(models.User, self.guest_id))

    def test_approval_preserves_account_points_roles_and_image(self):
        self.verify('approve')
        self.assertTrue(self.db.query(models.UserPassport).filter_by(user_id=self.guest_id).one().is_active)
        self.assertEqual(self.db.get(models.UserPoints, self.guest_id).points, 100)
        self.assertEqual(self.guest.roles[0].name, 'guest')
        self.image_delete.assert_not_called()
        with self.assertRaises(HTTPException) as caught:
            self.verify('reject')
        self.assertEqual(caught.exception.status_code, 409)

    def test_reject_cannot_remove_account_with_non_guest_role(self):
        self.guest.roles = self.actor.roles
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.verify()
        self.assertEqual(caught.exception.status_code, 409)
        self.assert_intact()

    def test_existing_history_is_preserved_instead_of_cascaded(self):
        self.db.add(models.Ticket(user_id=self.guest_id, subject='Synthetic history', message='Keep history', status='open'))
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.verify()
        self.assertEqual(caught.exception.status_code, 409)
        self.assert_intact()
        self.assertEqual(self.db.query(models.Ticket).count(), 1)

    def test_commit_failure_rolls_back_account_and_children_without_image_cleanup(self):
        with patch.object(self.db, 'commit', side_effect=SQLAlchemyError('simulated failure')):
            with self.assertRaises(HTTPException) as caught:
                self.verify()
        self.assertEqual(caught.exception.status_code, 503)
        self.assert_intact()
        self.assertEqual(self.db.query(models.UserRole).filter_by(user_id=self.guest_id).count(), 1)

    def test_unexpected_foreign_key_rolls_back_without_removing_history(self):
        self.db.add(models.PointPolicy(id=1, updated_by=self.guest_id))
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.verify()
        self.assertEqual(caught.exception.status_code, 409)
        self.assert_intact()
        self.assertEqual(self.db.get(models.PointPolicy, 1).updated_by, self.guest_id)

    def test_unknown_id_and_invalid_action_do_not_delete(self):
        with self.assertRaises(HTTPException) as caught:
            admin.verify_user(9999, admin.VerifyAction(action='reject'), self.actor, self.db)
        self.assertEqual(caught.exception.status_code, 404)
        with self.assertRaises(HTTPException) as caught:
            self.verify('invalid')
        self.assertEqual(caught.exception.status_code, 400)
        self.assert_intact()

    def test_http_rejection_requires_admin_and_succeeds_for_admin(self):
        app = FastAPI()
        app.include_router(admin.router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[users.get_current_user] = lambda: self.guest
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://unit.test') as client:
                denied = await client.put(f'/admin/users/{self.guest_id}/verify', json={'action': 'reject'})
                self.assertEqual(denied.status_code, 403)
                self.assert_intact()
                app.dependency_overrides[users.get_current_user] = lambda: self.actor
                accepted = await client.put(f'/admin/users/{self.guest_id}/verify', json={'action': 'reject'})
                self.assertEqual(accepted.status_code, 200)
        asyncio.run(flow())


if __name__ == '__main__':
    unittest.main()
