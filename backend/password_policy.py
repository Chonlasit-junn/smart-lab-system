"""One policy for newly set passwords; legacy login verification is unchanged."""

PASSWORD_POLICY_ERROR = (
    "Password must be 8-72 printable ASCII characters, include an uppercase "
    "letter and a number; symbols are optional and spaces are not allowed."
)
PASSWORD_RESET_POLICY_ERROR = PASSWORD_POLICY_ERROR


def validate_new_password(value: str) -> str:
    if (
        not 8 <= len(value) <= 72
        or any(not "!" <= character <= "~" for character in value)
        or not any("A" <= character <= "Z" for character in value)
        or not any("0" <= character <= "9" for character in value)
    ):
        raise ValueError(PASSWORD_POLICY_ERROR)
    return value  # Never trim, normalize or silently truncate a password.


def validate_password_reset(value: str) -> str:
    return validate_new_password(value)
