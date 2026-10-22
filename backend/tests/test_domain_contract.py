import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from url_policy import find_website_rule, normalize_domain

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "tests/fixtures/domain-contract.json").read_text(encoding="utf-8"))


class DomainContractTests(unittest.TestCase):
    def test_shared_normalization_vectors_and_idempotence(self):
        for value, expected in CONTRACT["normalization"]:
            with self.subTest(value=value):
                self.assertEqual(normalize_domain(value), expected)
                if expected:
                    self.assertEqual(normalize_domain(expected), expected)

    def test_shared_matching_vectors(self):
        for blocked, candidate, expected in CONTRACT["matching"]:
            rule = {"id": 1, "app_name": "Test only", "match_type": "website_domain",
                    "match_value": normalize_domain(blocked), "enabled": True}
            with self.subTest(blocked=blocked, candidate=candidate):
                self.assertEqual(find_website_rule([rule], candidate) is not None, expected)

    def test_backend_and_packaged_agent_sources_cannot_drift(self):
        self.assertEqual((ROOT / "backend/domain_normalization.py").read_bytes(),
                         (ROOT / "smart-lab-agent/domain_normalization.py").read_bytes())

    def test_dns_length_limits(self):
        self.assertIsNone(normalize_domain("a" * 64 + ".example"))
        self.assertIsNone(normalize_domain(".".join(["a" * 63] * 4)))
        self.assertIsNone(normalize_domain("a" * 4097))
