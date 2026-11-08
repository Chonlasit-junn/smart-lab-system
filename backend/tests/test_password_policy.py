import unittest
import sys
from pathlib import Path
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from password_policy import validate_new_password, validate_password_reset
from schemas import PasswordReset


class PasswordPolicyTests(unittest.TestCase):
    def test_registration_and_password_reset_share_policy_and_symbols_are_optional(self):
        for value in ['Password1', 'Password1!', 'A1bcdefg', 'A1' + 'x' * 70]:
            with self.subTest(length=len(value)):
                self.assertEqual(validate_new_password(value), value)
                self.assertEqual(validate_password_reset(value), value)
                request = PasswordReset(email='synthetic@example.com', otp='123456', new_password=value)
                self.assertEqual(request.new_password, value)

    def test_both_flows_reject_invalid_length_charset_or_missing_required_categories(self):
        for value in ['', 'short', ' ' * 8, 'x' * 73, 'ก' * 25, 'Password1ก', 'Password 1',
                      'password1', 'Password', '12345678', 'A1' + 'x' * 71]:
            with self.subTest(length=len(value)):
                with self.assertRaises(ValueError):
                    validate_new_password(value)
                with self.assertRaises(ValueError):
                    validate_password_reset(value)
                with self.assertRaises(ValidationError):
                    PasswordReset(email='synthetic@example.com', otp='123456', new_password=value)
