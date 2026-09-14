import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "upstream_sync",
    Path(__file__).resolve().parents[1] / "tools" / "upstream_sync.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


BASE = "1" * 40
NEXT = "2" * 40
TARGET = "src/main/kotlin/tsuki/site/all/Gelbooru.kt"


def registry():
    return {
        "schema": 1,
        "miyorare": {
            "repository": "Noirero/Miyorare",
            "branch": "beta",
            "packsManifest": "extensions/miyorare-sources/packs.json",
            "aliasManifest": "extensions/miyorare-sources/multi-upstream.json",
            "overlayRoot": "extensions/miyorare-sources/overlays",
        },
        "policy": {
            "autoUpdateByDefault": True,
            "manualOnlyOnIncompatibility": True,
            "publishOnlyAfterValidation": True,
            "keepLastKnownGoodOnFailure": True,
            "perSourceFailSafe": True,
            "protectMiyorareCustomization": True,
        },
        "protectedAreas": ["canonical-source-identity"],
        "providers": {
            "keiyoushi": {
                "repository": "keiyoushi/extensions-source",
                "branch": "main",
                "license": "Apache-2.0",
                "policy": "adapt-validate",
                "upstreamBase": BASE,
                "semanticBase": BASE,
                "lastKnownGood": BASE,
                "autoPromote": True,
                "semanticAdapters": ["domain-base-url", "literal-semantic"],
            },
            "uma": {
                "repository": "InvalidDavid/UMA",
                "branch": "master",
                "license": "GPL-3.0",
                "policy": "compatibility-layer",
                "upstreamBase": BASE,
                "lastKnownGood": BASE,
                "autoPromote": True,
            },
            "gekkoushi": {
                "repository": "Gekkoushi/plugin-source",
                "branch": "master",
                "license": "GPL-3.0",
                "policy": "three-way-overlay",
                "upstreamBase": BASE,
                "lastKnownGood": BASE,
                "autoPromote": True,
                "protectedOverlayTargets": [TARGET],
                "overlayBases": {TARGET: BASE},
            },
        },
    }


class UpstreamSyncRegistryTests(unittest.TestCase):
    def test_registry_with_semantic_and_overlay_bases_is_valid(self):
        MODULE.validate_registry(registry())

    def test_unknown_semantic_adapter_is_rejected(self):
        data = registry()
        data["providers"]["keiyoushi"]["semanticAdapters"].append("unsafe-magic")
        with self.assertRaises(SystemExit):
            MODULE.validate_registry(data)

    def test_missing_semantic_base_is_rejected(self):
        data = registry()
        del data["providers"]["keiyoushi"]["semanticBase"]
        with self.assertRaises(SystemExit):
            MODULE.validate_registry(data)

    def test_unknown_overlay_base_target_is_rejected(self):
        data = registry()
        data["providers"]["gekkoushi"]["overlayBases"]["other.kt"] = BASE
        with self.assertRaises(SystemExit):
            MODULE.validate_registry(data)

    def test_provider_promotion_does_not_advance_semantic_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(registry()), encoding="utf-8")
            MODULE.promote(path, "keiyoushi", NEXT)
            updated = json.loads(path.read_text(encoding="utf-8"))
            provider = updated["providers"]["keiyoushi"]
            self.assertEqual(NEXT, provider["lastKnownGood"])
            self.assertEqual(NEXT, provider["upstreamBase"])
            self.assertEqual(BASE, provider["semanticBase"])

    def test_overlay_base_can_advance_independently_from_provider_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(registry()), encoding="utf-8")
            MODULE.promote_overlay_base(path, "gekkoushi", TARGET, NEXT)
            updated = json.loads(path.read_text(encoding="utf-8"))
            provider = updated["providers"]["gekkoushi"]
            self.assertEqual(NEXT, provider["overlayBases"][TARGET])
            self.assertEqual(BASE, provider["lastKnownGood"])
            self.assertEqual(BASE, provider["upstreamBase"])


if __name__ == "__main__":
    unittest.main()
