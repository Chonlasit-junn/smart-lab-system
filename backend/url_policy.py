"""Domain-only website policy. Never persist paths, queries or credentials."""
from domain_normalization import domain_matches, normalize_domain


def find_website_rule(rules, domain):
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
