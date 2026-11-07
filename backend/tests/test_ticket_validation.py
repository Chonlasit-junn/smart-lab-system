import unittest

from pydantic import ValidationError

import schemas


class TicketValidationTests(unittest.TestCase):
    def test_subject_limit_accepts_255_characters(self):
        ticket = schemas.TicketCreate(subject="s" * 255, message="valid")
        self.assertEqual(len(ticket.subject), 255)

    def test_subject_limit_rejects_256_characters(self):
        with self.assertRaises(ValidationError):
            schemas.TicketCreate(subject="s" * 256, message="valid")

    def test_message_limit_accepts_5000_characters(self):
        ticket = schemas.TicketCreate(subject="valid", message="m" * 5000)
        self.assertEqual(len(ticket.message), 5000)

    def test_message_limit_rejects_5001_characters(self):
        with self.assertRaises(ValidationError):
            schemas.TicketCreate(subject="valid", message="m" * 5001)


if __name__ == "__main__":
    unittest.main()
