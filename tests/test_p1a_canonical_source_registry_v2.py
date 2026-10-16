import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("registry_v2", ROOT / "tools/canonical_source_registry_v2.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def legacy_source(**overrides):
    value = {
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
    }
    value.update(overrides)
    return value


class CanonicalSourceRegistryV2Tests(unittest.TestCase):
    def test_migration_preserves_identity_provider_and_lkg_without_language_pack_inference(self) -> None:
        old = legacy_source()
        farm = {"schemaVersion": 1, "providerBaselines": {"keiyoushi": "abc"}, "sources": [old]}
        result = MODULE.migrate(farm)
        source = result["sources"][0]
        self.assertEqual(source["canonicalId"], old["canonicalId"])
        self.assertEqual(source["providers"], old["upstreamIdentities"])
        self.assertEqual(source["compatibility"]["lastKnownGood"], old["lastKnownGood"])
        self.assertEqual(source["packs"], [])
        self.assertEqual(source["lifecycle"]["state"], "held")
        self.assertEqual(source["compatibility"]["health"], "HELD")
        self.assertEqual(source["lifecycle"]["reason"], "PACK_MEMBERSHIP_UNDECLARED")
        self.assertEqual(source["origin"]["authority"], "legacy-upstream-identities")

    def test_explicit_global_membership_is_independent_of_language(self) -> None:
        result = MODULE.migrate({"schemaVersion": 1, "sources": [legacy_source(language="en", packs=["miyorare-global"])]})
        source = result["sources"][0]
        self.assertEqual(source["packs"], ["miyorare-global"])
        self.assertEqual(source["lifecycle"]["state"], "active")

    def test_explicit_native_origin_wins_without_provider_inference(self) -> None:
        old = legacy_source(
            packs=["miyorare-en"],
            origin={"kind": "miyorare-native", "providers": []},
            upstreamIdentities={},
            providers=[],
        )
        source = MODULE.migrate({"schemaVersion": 1, "sources": [old]})["sources"][0]
        self.assertEqual(source["origin"]["kind"], "miyorare-native")
        self.assertEqual(source["origin"]["authority"], "source-declaration")

    def test_origin_without_declaration_or_upstream_identity_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.migrate({"schemaVersion": 1, "sources": [legacy_source(upstreamIdentities={})]})

    def test_unknown_metadata_does_not_invent_identity(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.migrate({"schemaVersion": 1, "sources": [{"canonicalId": None}]})

    def test_duplicate_provider_identity_fails_closed(self) -> None:
        base = {
            "displayName": "A", "language": "en", "packs": ["miyorare-en"],
            "origin": {"kind": "upstream-derived", "providers": ["keiyoushi"], "authority": "source-declaration"},
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
