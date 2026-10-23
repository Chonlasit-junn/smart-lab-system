"""Phone-number validation shared by account registration endpoints."""

import re


_PHONE_CHARACTERS = re.compile(r"^\+?[0-9().\s-]+$")
_PHONE_DIGITS = re.compile(r"[0-9]")


def normalize_phone_number(value):
    """Accept formatted international numbers but reject arbitrary text."""
    phone = str(value or "").strip()
    if not _PHONE_CHARACTERS.fullmatch(phone):
        raise ValueError("Invalid phone number.")
    digits = "".join(_PHONE_DIGITS.findall(phone))
    if not 9 <= len(digits) <= 15:
        raise ValueError("Invalid phone number.")
    return digits
