import unittest
import sys
from pathlib import Path
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from password_policy import validate_new_password
from schemas import PasswordReset


class PasswordPolicyTests(unittest.TestCase):
    def test_registration_and_recovery_accept_identical_passwords_unchanged(self):
        for value in ['12345678', 'x' * 72, 'ก' * 24, '😀' * 8, ' padded password ']:
            with self.subTest(length=len(value)):
                self.assertEqual(validate_new_password(value), value)
                request = PasswordReset(email='synthetic@example.com', otp='123456', new_password=value)
                self.assertEqual(request.new_password, value)

    def test_registration_and_recovery_reject_identical_invalid_passwords(self):
        for value in ['', 'short', ' ' * 8, 'x' * 73, 'ก' * 25, '😀' * 4]:
            with self.subTest(length=len(value)):
                with self.assertRaises(ValueError):
                    validate_new_password(value)
                with self.assertRaises(ValidationError):
                    PasswordReset(email='synthetic@example.com', otp='123456', new_password=value)
