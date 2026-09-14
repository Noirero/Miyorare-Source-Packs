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
                "lastKnownGood": BASE,
                "autoPromote": True,
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
    def test_overlay_base_registry_is_valid(self):
        MODULE.validate_registry(registry())

    def test_unknown_overlay_base_target_is_rejected(self):
        data = registry()
        data["providers"]["gekkoushi"]["overlayBases"]["other.kt"] = BASE
        with self.assertRaises(SystemExit):
            MODULE.validate_registry(data)

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
