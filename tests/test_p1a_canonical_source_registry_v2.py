import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("registry_v2", ROOT / "tools/canonical_source_registry_v2.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class CanonicalSourceRegistryV2Tests(unittest.TestCase):
    def test_migration_preserves_identity_provider_and_lkg(self) -> None:
        farm = {
            "schemaVersion": 1,
            "providerBaselines": {"keiyoushi": "abc"},
            "sources": [{
                "canonicalId": "miyorare:miyorare-en:EXAMPLE",
                "displayName": "Example",
                "language": "en",
                "providers": ["keiyoushi"],
                "upstreamIdentities": {"keiyoushi": {"module": "src/en/example", "sourceId": 123}},
                "lastKnownGood": {"keiyoushi": "lkg"},
                "currentVersion": {"keiyoushi": "current"},
                "runtimeHealth": "HEALTHY",
                "compatibilityBaseline": {"status": "VALIDATED"},
                "approvalState": "APPROVED",
                "publishEligible": True,
                "protectedOverlays": [],
            }],
        }
        result = MODULE.migrate(farm)
        source = result["sources"][0]
        self.assertEqual(source["canonicalId"], farm["sources"][0]["canonicalId"])
        self.assertEqual(source["providers"], farm["sources"][0]["upstreamIdentities"])
        self.assertEqual(source["compatibility"]["lastKnownGood"], farm["sources"][0]["lastKnownGood"])
        self.assertEqual(source["packs"], ["miyorare-en"])
        self.assertEqual(source["lifecycle"]["state"], "active")

    def test_unknown_metadata_does_not_invent_identity(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.migrate({"schemaVersion": 1, "sources": [{"canonicalId": None}]})

    def test_duplicate_provider_identity_fails_closed(self) -> None:
        base = {
            "displayName": "A", "language": "en", "packs": ["miyorare-en"],
            "origin": {"kind": "upstream-derived", "providers": ["keiyoushi"]},
            "providers": {"keiyoushi": {"module": "same", "sourceId": 1}},
            "lifecycle": {"state": "candidate", "ownerActionRequired": False},
            "compatibility": {"health": "UNKNOWN", "baseline": {}, "lastKnownGood": {}, "currentVersion": {}},
        }
        first = dict(base, canonicalId="miyorare:inventory-en:A")
        second = dict(base, canonicalId="miyorare:inventory-en:B")
        with self.assertRaises(ValueError):
            MODULE.validate({"schemaVersion": 2, "kind": "MIYORARE_CANONICAL_SOURCE_REGISTRY", "sources": [first, second]})


if __name__ == "__main__":
    unittest.main()
