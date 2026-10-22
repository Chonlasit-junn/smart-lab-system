"""One policy for newly set passwords; legacy login verification is unchanged."""

PASSWORD_POLICY_ERROR = "Password must be 8 or more characters and at most 72 UTF-8 bytes."


def validate_new_password(value: str) -> str:
    if len(value) < 8 or not value.strip() or len(value.encode("utf-8")) > 72:
        raise ValueError(PASSWORD_POLICY_ERROR)
    return value  # Never trim, normalize or silently truncate a password.
