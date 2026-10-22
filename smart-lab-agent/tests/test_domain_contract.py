import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_policy import find_website_match, normalize_rules
from browser_url import normalize_domain

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "tests/fixtures/domain-contract.json").read_text(encoding="utf-8"))


class AgentDomainContractTests(unittest.TestCase):
    def test_shared_normalization_vectors_and_idempotence(self):
        for value, expected in CONTRACT["normalization"]:
            with self.subTest(value=value):
                self.assertEqual(normalize_domain(value), expected)
                if expected:
                    self.assertEqual(normalize_domain(expected), expected)

    def test_website_policy_from_canonical_frontend_domain(self):
        for blocked, candidate, expected in CONTRACT["matching"]:
            rules = normalize_rules([{"id": 1, "app_name": "Offline test", "match_type": "website_domain",
                                      "match_value": normalize_domain(blocked), "enabled": True}])
            with self.subTest(blocked=blocked, candidate=candidate):
                self.assertEqual(find_website_match(rules, candidate) is not None, expected)

    def test_disabled_rules_still_do_not_match(self):
        rule = {"id": 1, "app_name": "Disabled", "match_type": "website_domain",
                "match_value": "xn--fa-hia.de", "enabled": False}
        self.assertIsNone(find_website_match([rule], "faß.de"))
