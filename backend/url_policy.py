"""Domain-only website policy. Never persist paths, queries or credentials."""
import ipaddress
import re
from urllib.parse import urlsplit


def normalize_domain(value):
    raw = str(value or "").strip()
    if not raw or len(raw) > 4096 or any(char.isspace() or ord(char) < 32 for char in raw):
        return None
    try:
        parsed = urlsplit(raw if "://" in raw else "https://" + raw)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return None
        parsed.port
        host = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
        try:
            return str(ipaddress.ip_address(host))
        except ValueError:
            pass
        if len(host) > 253 or "." not in host:
            return None
        if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                   for label in host.split(".")):
            return None
        return host
    except (ValueError, UnicodeError):
        return None


def find_website_rule(rules, domain):
    host = normalize_domain(domain)
    if not host:
        return None
    for rule in rules:
        if rule.get("enabled") is False or rule.get("match_type") != "website_domain":
            continue
        blocked = normalize_domain(rule.get("match_value"))
        if blocked and (host == blocked or host.endswith("." + blocked)):
            return rule
    return None
