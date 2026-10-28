"""Bounded, thread-safe login throttling for the single API worker.

No database writes or raw client identifiers. A multi-worker deployment needs
a shared limiter at its trusted gateway before scaling the API worker count.
"""

import hashlib
import hmac
import ipaddress
import math
import secrets
import threading
import time
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm

from utils import normalize_email, pwd_context

INVALID_LOGIN = "Invalid email or password."
LIMITED_LOGIN = "Too many login attempts. Please try again later."


class LoginLimiter:
    def __init__(self, *, clock=time.monotonic, max_entries=4096):
        self.clock = clock
        self.max_entries = max_entries
        self.entries = {}
        self.lock = threading.Lock()
        self.key = secrets.token_bytes(32)

    def _identity(self, kind, value):
        return hmac.new(self.key, f"{kind}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()

    def check(self, ip, email):
        try:
            ip = ipaddress.ip_address(ip).compressed
        except ValueError:
            ip = str(ip).strip().lower()
        budgets = [
            ("global", 300, 60),
            (self._identity("ip", ip), 60, 60),
            (self._identity("account", normalize_email(email)), 10, 300),
        ]
        with self.lock:
            now = self.clock()
            self.entries = {key: row for key, row in self.entries.items() if row[1] > now}
            retry = 0
            for key, limit, _window in budgets:
                count, until = self.entries.get(key, (0, now))
                if count >= limit:
                    retry = max(retry, math.ceil(until - now))
            if len(self.entries) + sum(key not in self.entries for key, _, _ in budgets) > self.max_entries:
                retry = max(retry, 60)
            if retry:
                raise HTTPException(429, LIMITED_LOGIN, headers={"Retry-After": str(max(1, retry))})
            for key, _limit, window in budgets:
                count, until = self.entries.get(key, (0, now + window))
                self.entries[key] = (count + 1, until)


login_limiter = LoginLimiter()


def enforce_login_limits(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    # Trust the ASGI peer only; forwarded headers are the server/proxy's job.
    login_limiter.check(request.client.host if request.client else "unknown", form_data.username)
    if len(form_data.username) > 254 or len(form_data.password.encode("utf-8")) > 72:
        raise HTTPException(401, INVALID_LOGIN)


@lru_cache(maxsize=1)
def _dummy_hash():
    return pwd_context.hash(secrets.token_urlsafe(32))


def password_matches(password, stored_hash):
    if len(password.encode("utf-8")) > 72:
        return False
    try:
        valid = pwd_context.verify(password, stored_hash or _dummy_hash())
    except (ValueError, TypeError):
        return False
    return bool(stored_hash and valid)
