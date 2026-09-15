import copy
import json
import unittest
from pathlib import Path

from tools.source_registry import RegistryError, summary, validate_registry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "compatibility" / "source-registry.json"


def load_registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


class SourceRegistryTests(unittest.TestCase):
    def test_seed_registry_is_valid_and_balanced(self):
        registry = load_registry()
        validate_registry(registry)
        report = summary(registry)
        self.assertEqual(report["sourceCount"], 12)
        self.assertGreaterEqual(report["languages"]["id"], 5)
        self.assertGreaterEqual(report["languages"]["en"], 5)
        self.assertIn("COOKIE", report["authTypes"])
        self.assertIn("NO_AUTH", report["authTypes"])

    def test_all_three_providers_are_exercised(self):
        report = summary(load_registry())
        self.assertEqual(set(report["providerMemberships"]), {"keiyoushi", "uma", "gekkoushi"})
        self.assertGreaterEqual(len(report["adapterFamilies"]), 6)

    def test_hold_cannot_become_owner_assignment(self):
        registry = load_registry()
        mutated = copy.deepcopy(registry)
        mutated["sources"][0]["repairPolicy"]["holdRequiresOwnerAction"] = True
        with self.assertRaises(RegistryError):
            validate_registry(mutated)

    def test_identity_versions_must_match_provider_membership(self):
        registry = load_registry()
        mutated = copy.deepcopy(registry)
        del mutated["sources"][0]["lastKnownGood"]["keiyoushi"]
        with self.assertRaises(RegistryError):
            validate_registry(mutated)

    def test_generic_compatibility_capabilities_cannot_be_dropped(self):
        registry = load_registry()
        mutated = copy.deepcopy(registry)
        mutated["sources"][0]["compatibilityBaseline"]["capabilities"].remove("reader")
        with self.assertRaises(RegistryError):
            validate_registry(mutated)


if __name__ == "__main__":
    unittest.main()
