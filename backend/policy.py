"""Shared Backend helpers for Agent policy serialization and validation."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

import models
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from time_utils import utc_now
from utils import ALGORITHM, SECRET_KEY
from url_policy import find_website_rule


DEFAULT_MATCH_TYPE = "process_name"
SUPPORTED_MATCH_TYPES = frozenset(
    {
        "process_name",
        "process_name_or_title",
        "exe_path",
        "window_title",
        "website_domain",
    }
)


def normalize_compact(value: Any) -> str:
    """Normalize names/titles for case-insensitive, punctuation-tolerant matching."""

    return "".join(
        character
        for character in str(value or "").casefold()
        if character.isalnum()
    )


def normalize_process_name(value: Any) -> str:
    """Return a process basename without a Windows .exe suffix."""

    raw_value = str(value or "").strip().replace("/", "\\")
    basename = raw_value.rsplit("\\", 1)[-1]
    if basename.casefold().endswith(".exe"):
        basename = basename[:-4]
    return normalize_compact(basename)


def normalize_path(value: Any) -> str:
    """Normalize a Windows executable path for exact comparison."""

    return str(value or "").strip().strip('"').replace("/", "\\").casefold().rstrip("\\")


def serialize_rule(app: models.BlacklistedApp, include_created_at: bool = False) -> dict[str, Any]:
    """Serialize a DB row without returning an ORM object to the Agent."""

    match_type = (getattr(app, "match_type", None) or DEFAULT_MATCH_TYPE).strip().casefold()
    if match_type not in SUPPORTED_MATCH_TYPES:
        match_type = DEFAULT_MATCH_TYPE

    result: dict[str, Any] = {
        "id": app.id,
        "app_name": app.app_name,
        "description": app.description,
        "match_type": match_type,
        "match_value": (
            getattr(app, "match_value", None) or app.app_name
        ).strip(),
        "enabled": bool(getattr(app, "enabled", True)),
    }
    if include_created_at:
        result["created_at"] = app.created_at
    return result


def get_policy_rules(db: Session, enabled_only: bool = True) -> list[dict[str, Any]]:
    query = db.query(models.BlacklistedApp)
    if enabled_only:
        query = query.filter(models.BlacklistedApp.enabled.is_(True))
    apps = query.order_by(models.BlacklistedApp.id.asc()).all()
    return [serialize_rule(app) for app in apps]


def build_policy(rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a deterministic policy payload and short content version."""

    canonical = json.dumps(
        rules,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    version = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return {"version": version, "data": rules}


def sign_policy_snapshot(policy: dict[str, Any]) -> str:
    """Preserve server-issued rules for events delivered after a policy change."""

    return jwt.encode(
        {
            "purpose": "agent_policy_snapshot",
            "version": policy["version"],
            "data": policy["data"],
            "issued_at": int(utc_now().timestamp()),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_policy_snapshot(token: str) -> dict[str, Any]:
    """Accept only signed policy data, never an Agent's unsigned rule snapshot.

    No expiry is imposed: a durable outbox may be offline for a long time.
    The caller checks the detection time against issuance and session times.
    """

    try:
        snapshot = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if (
            snapshot.get("purpose") != "agent_policy_snapshot"
            or not isinstance(snapshot.get("data"), list)
            or not isinstance(snapshot.get("issued_at"), int)
            or snapshot.get("version") != build_policy(snapshot["data"])["version"]
        ):
            raise ValueError("Invalid policy snapshot.")
        return snapshot
    except (JWTError, TypeError, KeyError, ValueError) as exc:
        raise ValueError("Invalid policy snapshot.") from exc


def find_matching_rule(
    rules: list[dict[str, Any]],
    *,
    process_name: Optional[str] = None,
    exe_path: Optional[str] = None,
    window_title: Optional[str] = None,
    executable_identity: Optional[dict[str, str]] = None,
    browser_domain: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Validate Agent evidence against the active policy rules."""

    if not isinstance(executable_identity, dict):
        return None
    if browser_domain is not None:
        if str(executable_identity.get("original_filename") or "").casefold() not in {"chrome.exe", "msedge.exe"}:
            return None
        return find_website_rule(rules, browser_domain)
    original = normalize_process_name(
        executable_identity.get("original_filename") or executable_identity.get("internal_name")
    )
    product = normalize_compact(executable_identity.get("product_name"))
    normalized_exe_path = normalize_path(exe_path)

    for rule in rules:
        if rule.get("enabled") is False:
            continue

        match_type = rule.get("match_type") or DEFAULT_MATCH_TYPE
        match_value = str(rule.get("match_value") or rule.get("app_name") or "")
        if not match_value:
            continue

        # Legacy mixed rules now use executable identity only. Titles remain telemetry.
        if match_type in {"window_title", "website_domain"} or match_type not in SUPPORTED_MATCH_TYPES:
            continue
        if match_type == "exe_path" and normalized_exe_path != normalize_path(match_value):
            continue
        expected = {normalize_process_name(match_value)}
        if match_type == "exe_path":
            expected.add(normalize_process_name(rule.get("app_name")))
        expected.discard("")
        if original:
            if original in expected:
                return rule
        elif product:
            aliases = {"starrail": {"starrail", "honkaistarrail"}}
            if any(product in aliases.get(name, {name}) for name in expected):
                return rule

    return None
