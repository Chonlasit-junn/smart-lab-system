"""Policy normalization and matching helpers for the Windows Agent.

The helpers in this module intentionally have no GUI or network dependency so
that policy behavior can be tested without starting the Agent window.
"""

from __future__ import annotations

from typing import Any, Optional
from browser_url import normalize_domain
from domain_normalization import domain_matches


SUPPORTED_MATCH_TYPES = frozenset(
    {
        "process_name",
        "process_name_or_title",
        "exe_path",
        "window_title",
        "website_domain",
    }
)


DEFAULT_FALLBACK_RULES = [
    {
        "id": None,
        "app_name": "BitTorrent",
        "match_type": "process_name",
        "match_value": "bittorrent",
        "enabled": True,
    },
    {
        "id": None,
        "app_name": "CheatEngine",
        "match_type": "process_name",
        "match_value": "cheatengine",
        "enabled": True,
    },
    {
        "id": None,
        "app_name": "GenshinImpact",
        "match_type": "process_name",
        "match_value": "genshinimpact",
        "enabled": True,
    },
    {
        "id": None,
        "app_name": "StarRail",
        "match_type": "process_name",
        "match_value": "starrail",
        "enabled": True,
    },
]


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


def normalize_rules(raw_rules: Any) -> list[dict[str, Any]]:
    """Validate and normalize the policy payload returned by the Backend."""

    if not isinstance(raw_rules, list):
        return []

    rules: list[dict[str, Any]] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict) or raw_rule.get("enabled") is False:
            continue

        app_name = str(raw_rule.get("app_name") or "").strip()
        match_type = str(
            raw_rule.get("match_type") or "process_name"
        ).strip().casefold()
        match_value = str(raw_rule.get("match_value") or app_name).strip()
        if not app_name or not match_value or match_type not in SUPPORTED_MATCH_TYPES:
            continue

        rules.append(
            {
                "id": raw_rule.get("id"),
                "app_name": app_name,
                "match_type": match_type,
                "match_value": match_value,
                "enabled": True,
            }
        )

    return rules


def find_process_match(
    rules: list[dict[str, Any]],
    process_name: Any,
    exe_path: Optional[Any] = None,
    executable_identity: Optional[dict[str, str]] = None,
) -> Optional[dict[str, Any]]:
    """Match embedded EXE identity; observed names/titles cannot prove identity."""

    if not isinstance(executable_identity, dict):
        return None
    original = executable_identity.get("original_filename") or executable_identity.get("internal_name")
    original = normalize_process_name(original)
    product = normalize_compact(executable_identity.get("product_name"))
    normalized_exe_path = normalize_path(exe_path)

    for rule in rules:
        if rule.get("enabled") is False:
            continue
        match_type = rule["match_type"]
        match_value = rule["match_value"]
        if match_type in {"window_title", "website_domain"}:
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
            # Product-only resources use exact labels, not title substrings.
            aliases = {"starrail": {"starrail", "honkaistarrail"}}
            if any(product in aliases.get(name, {name}) for name in expected):
                return rule

    return None


def find_window_match(
    rules: list[dict[str, Any]],
    window_title: Any,
) -> Optional[dict[str, Any]]:
    """Window titles are telemetry only, never grounds for a penalty."""
    return None


def find_website_match(rules, domain):
    host = normalize_domain(domain)
    if not host:
        return None
    for rule in rules:
        if rule.get("enabled") is False or rule.get("match_type") != "website_domain":
            continue
        blocked = normalize_domain(rule.get("match_value"))
        if blocked and domain_matches(host, blocked):
            return rule
    return None
