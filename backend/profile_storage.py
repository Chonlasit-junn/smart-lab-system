"""Profile-image storage helpers.

Images are kept in the local filesystem during development. Production can
use a private Supabase Storage bucket by setting ``PROFILE_STORAGE_BACKEND``
to ``supabase`` and providing the service-role key to the Backend only.
"""

from __future__ import annotations

import os
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv()

PROFILE_STORAGE_BACKEND = (
    os.getenv("PROFILE_STORAGE_BACKEND") or "local"
).strip().lower()
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
SUPABASE_PROFILE_BUCKET = (
    os.getenv("SUPABASE_PROFILE_BUCKET") or "profile-images"
).strip()

try:
    PROFILE_SIGNED_URL_TTL = max(
        60,
        int(os.getenv("PROFILE_SIGNED_URL_TTL") or "3600"),
    )
except ValueError:
    PROFILE_SIGNED_URL_TTL = 3600


class ProfileStorageError(RuntimeError):
    """Raised when a profile image cannot be stored or signed."""


def uses_supabase_storage() -> bool:
    return PROFILE_STORAGE_BACKEND == "supabase"


def profile_object_path(user_id: int) -> str:
    """Return a stable, non-identifying object path for one user's avatar."""

    return f"profiles/{user_id}/avatar.jpg"


def _require_supabase_config() -> None:
    if not uses_supabase_storage():
        raise ProfileStorageError(
            "Supabase profile storage is not enabled."
        )
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise ProfileStorageError(
            "Supabase profile storage is not configured."
        )
    if not SUPABASE_PROFILE_BUCKET:
        raise ProfileStorageError("Supabase profile bucket is not configured.")


def _object_url(path: str, endpoint: str = "object") -> str:
    encoded_path = quote(path.lstrip("/"), safe="/")
    return (
        f"{SUPABASE_URL}/storage/v1/{endpoint}/"
        f"{quote(SUPABASE_PROFILE_BUCKET, safe='')}/{encoded_path}"
    )


def _bucket_object_url() -> str:
    return (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{quote(SUPABASE_PROFILE_BUCKET, safe='')}"
    )


def _auth_headers(content_type: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


async def upload_profile_image(path: str, image_data: bytes) -> None:
    """Upload a normalized JPEG to the configured private bucket."""

    _require_supabase_config()
    headers = _auth_headers("image/jpeg")
    headers.update({"x-upsert": "true", "cache-control": "3600"})

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                _object_url(path),
                content=image_data,
                headers=headers,
            )
        response.raise_for_status()
    except (httpx.HTTPError, ProfileStorageError) as exc:
        raise ProfileStorageError("Profile image upload failed.") from exc


async def delete_profile_image(path: str) -> None:
    """Best-effort cleanup used when a database transaction fails."""

    if not uses_supabase_storage() or not path:
        return
    try:
        _require_supabase_config()
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.delete(
                _bucket_object_url(),
                json={"prefixes": [path]},
                headers=_auth_headers(),
            )
        response.raise_for_status()
    except (httpx.HTTPError, ProfileStorageError):
        # Cleanup must not hide the original registration/database error.
        return


def delete_profile_image_sync(path: str | None) -> None:
    """Best-effort cleanup for synchronous admin deletion flows."""

    if not uses_supabase_storage() or not path:
        return
    try:
        _require_supabase_config()
        response = httpx.delete(
            _bucket_object_url(),
            json={"prefixes": [path]},
            headers=_auth_headers(),
            timeout=20,
        )
        response.raise_for_status()
    except (httpx.HTTPError, ProfileStorageError):
        return


def get_profile_image_url(profile_pic: str | None) -> str | None:
    """Resolve the database path to a frontend-safe URL.

    Supabase paths receive a short-lived signed URL. Legacy local paths are
    returned unchanged so the existing Backend ``/uploads`` route continues
    to work during development and migration.
    """

    if not profile_pic:
        return None
    if profile_pic.startswith(("http://", "https://")):
        return profile_pic
    if not uses_supabase_storage() or not profile_pic.startswith("profiles/"):
        return profile_pic

    try:
        _require_supabase_config()
        response = httpx.post(
            _object_url(profile_pic, endpoint="object/sign"),
            json={"expiresIn": PROFILE_SIGNED_URL_TTL},
            headers=_auth_headers("application/json"),
            timeout=10,
        )
        response.raise_for_status()
        signed_url = response.json().get("signedURL")
        if not signed_url:
            raise ProfileStorageError("Supabase did not return a signed URL.")
        if signed_url.startswith("http://") or signed_url.startswith("https://"):
            return signed_url
        if signed_url.startswith("/storage/v1"):
            return f"{SUPABASE_URL}{signed_url}"
        if signed_url.startswith("/"):
            return f"{SUPABASE_URL}/storage/v1{signed_url}"
        return f"{SUPABASE_URL}/storage/v1/{signed_url}"
    except (httpx.HTTPError, ProfileStorageError, ValueError, TypeError):
        # A missing avatar should not make an otherwise healthy profile API
        # fail. The next profile request will try signing again.
        return None
