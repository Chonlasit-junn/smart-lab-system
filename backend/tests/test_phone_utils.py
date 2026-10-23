"""Registration phone validation tests; no external services are used."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phone_utils import normalize_phone_number


class PhoneNumberTests(unittest.TestCase):
    def test_normalizes_valid_formatted_numbers(self):
        self.assertEqual(normalize_phone_number("081-234-5678"), "0812345678")
        self.assertEqual(normalize_phone_number("+66 (81) 234 5678"), "66812345678")

    def test_rejects_missing_text_and_invalid_length(self):
        for value in (None, "", "user@example.com", "12345678", "1" * 16, "call 0812345678"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_phone_number(value)


if __name__ == "__main__":
    unittest.main()
