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
PROFILE_SIGNED_URL_BATCH_SIZE = 100


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


def _bucket_sign_url() -> str:
    return (
        f"{SUPABASE_URL}/storage/v1/object/sign/"
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


def _frontend_signed_url(signed_url: str) -> str:
    if signed_url.startswith(("http://", "https://")):
        return signed_url
    if signed_url.startswith("/storage/v1"):
        return f"{SUPABASE_URL}{signed_url}"
    if signed_url.startswith("/"):
        return f"{SUPABASE_URL}/storage/v1{signed_url}"
    return f"{SUPABASE_URL}/storage/v1/{signed_url}"


def get_profile_image_urls(profile_pics: list[str | None]) -> list[str | None]:
    """Resolve local, external, and private Supabase avatar paths in one batch."""
    resolved = []
    private_paths = []
    for profile_pic in profile_pics:
        if not profile_pic or profile_pic.startswith(("http://", "https://")):
            resolved.append(profile_pic)
        elif uses_supabase_storage() and profile_pic.startswith("profiles/"):
            resolved.append(None)
            private_paths.append(profile_pic)
        else:
            resolved.append(profile_pic)

    if not private_paths:
        return resolved

    try:
        _require_supabase_config()
        unique_paths = list(dict.fromkeys(private_paths))
        signed_by_path = {}
        for offset in range(0, len(unique_paths), PROFILE_SIGNED_URL_BATCH_SIZE):
            batch = unique_paths[offset:offset + PROFILE_SIGNED_URL_BATCH_SIZE]
            try:
                response = httpx.post(
                    _bucket_sign_url(),
                    json={"expiresIn": PROFILE_SIGNED_URL_TTL, "paths": batch},
                    headers=_auth_headers("application/json"),
                    timeout=10,
                )
                response.raise_for_status()
                signed_rows = response.json()
                if not isinstance(signed_rows, list):
                    continue
                for row in signed_rows:
                    if not isinstance(row, dict):
                        continue
                    path = row.get("path")
                    signed_url = row.get("signedURL") or row.get("signedUrl")
                    if (
                        path in batch
                        and isinstance(signed_url, str)
                        and signed_url
                        and not row.get("error")
                    ):
                        signed_by_path[path] = _frontend_signed_url(signed_url)
            except (httpx.HTTPError, ProfileStorageError, ValueError, TypeError):
                # A signing failure should not fail an otherwise healthy list API.
                continue
        return [
            signed_by_path.get(profile_pic)
            if profile_pic and uses_supabase_storage() and profile_pic.startswith("profiles/")
            else value
            for profile_pic, value in zip(profile_pics, resolved)
        ]
    except (httpx.HTTPError, ProfileStorageError, ValueError, TypeError):
        return resolved


def get_profile_image_url(profile_pic: str | None) -> str | None:
    """Resolve one profile path using the same batch signing implementation."""
    return get_profile_image_urls([profile_pic])[0]
