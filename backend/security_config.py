"""Security settings shared by token creation, validation and API startup."""

import logging
import os
import secrets
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()
ALGORITHM = "HS256"
_development_key = secrets.token_urlsafe(48)
_warned = False


def is_production(environ):
    return bool(environ.get("SPACE_ID")) or environ.get("SMART_LAB_ENV", "development").lower() != "development"


def jwt_secret(environ=None):
    global _warned
    env = os.environ if environ is None else environ
    key = env.get("SECRET_KEY", "")
    if key:
        if len(key.encode("utf-8")) < 32:
            raise RuntimeError("SECRET_KEY must be a private random value of at least 32 bytes.")
        return key
    if is_production(env):
        raise RuntimeError("SECRET_KEY is required in production.")
    if not _warned:
        logging.getLogger(__name__).warning(
            "No SECRET_KEY configured for development; sessions expire on API restart."
        )
        _warned = True
    return _development_key


def cors_origins(environ=None):
    env = os.environ if environ is None else environ
    value = env.get("CORS_ALLOWED_ORIGINS", "")
    if not value.strip():
        if is_production(env):
            raise RuntimeError("CORS_ALLOWED_ORIGINS must list the frontend origins in production.")
        return [f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 5174)]
    origins = []
    for origin in value.split(","):
        origin = origin.strip().rstrip("/")
        parts = urlsplit(origin)
        if (
            parts.scheme not in {"https", "http"} or not parts.hostname
            or parts.username or parts.password or parts.path or parts.query or parts.fragment
            or "*" in origin
            or (is_production(env) and parts.scheme != "https")
        ):
            raise RuntimeError("CORS_ALLOWED_ORIGINS must contain exact origins (HTTPS in production).")
        # Validate malformed ports as well, without echoing environment values.
        try:
            parts.port
        except ValueError:
            raise RuntimeError("CORS_ALLOWED_ORIGINS contains an invalid port.") from None
        if origin not in origins:
            origins.append(origin)
    return origins


SECRET_KEY = jwt_secret()
