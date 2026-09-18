import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "source_pack_manifest",
    Path(__file__).resolve().parents[1] / "tools" / "source_pack_manifest.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SHA1 = "1" * 40
SHA2 = "2" * 40
SHA3 = "3" * 40
SHA4 = "4" * 40
FARM_SHA = "5" * 40
CONTRACT_SHA = "f" * 64


def contract():
    return {
        "format": {
            "releaseManifestSchema": 3,
            "maxArtifactBytes": 67108864,
        },
        "compatibility": {
            "stableChannel": "stable",
            "compatibilityEpoch": 1,
            "tsukiApi": "1.0.5",
        },
    }


def manifest():
    return {
        "schema": 3,
        "version": "1.2.3",
        "tag": "miyorare-sources-v1.2.3",
        "compatibility": {
            "channel": "stable",
            "tsukiApi": "1.0.5",
            "compatibilityEpoch": 1,
            "minMiyorareVersionCode": 75,
            "maxMiyorareVersionCode": None,
            "requiredLogicalPacks": ["miyorare-id", "miyorare-en", "miyorare-global"],
            "releaseLockRequired": True,
        },
        "sourceRepository": "Noirero/Miyorare",
        "sourceBranch": "beta",
        "sourceCommit": SHA1,
        "runtimeCompatibility": {
            "repository": "Noirero/Miyorare",
            "branch": "main",
            "commit": SHA2,
            "versionCode": 75,
            "tsukiApi": "1.0.5",
        },
        "upstreams": {
            "uma": SHA2,
            "gekkoushi": SHA3,
            "keiyoushi": SHA4,
        },
        "compatibilitySnapshotId": MODULE.compatibility_snapshot_id(
            CONTRACT_SHA,
            SHA2,
            SHA1,
            FARM_SHA,
            {"uma": SHA2, "gekkoushi": SHA3, "keiyoushi": SHA4},
        ),
        "compatibilitySnapshot": {
            "schemaVersion": 1,
            "algorithm": "sha256",
            "contractSha256": CONTRACT_SHA,
            "farmCommit": FARM_SHA,
        },
        "packs": [
            {
                "pluginId": "miyorare-id",
                "language": "id",
                "sourceCount": 2,
                "shards": [
                    {"provider": "UMA", "pluginId": "miyorare-id", "assetName": "miyorare-id-uma.jar", "size": 10, "sha256": "a" * 64, "sourceCount": 1},
                    {"provider": "GEKKOUSHI", "pluginId": "miyorare-id-gekkoushi", "assetName": "miyorare-id-gekkoushi.jar", "size": 11, "sha256": "b" * 64, "sourceCount": 1},
                ],
            },
            {
                "pluginId": "miyorare-en",
                "language": "en",
                "sourceCount": 2,
                "shards": [
                    {"provider": "UMA", "pluginId": "miyorare-en", "assetName": "miyorare-en-uma.jar", "size": 12, "sha256": "c" * 64, "sourceCount": 1},
                    {"provider": "GEKKOUSHI", "pluginId": "miyorare-en-gekkoushi", "assetName": "miyorare-en-gekkoushi.jar", "size": 13, "sha256": "d" * 64, "sourceCount": 1},
                ],
            },
            {
                "pluginId": "miyorare-global",
                "language": "all",
                "sourceCount": 2,
                "shards": [
                    {"provider": "GEKKOUSHI", "pluginId": "miyorare-global", "assetName": "miyorare-global-gekkoushi.jar", "size": 14, "sha256": "e" * 64, "sourceCount": 2},
                ],
            },
        ],
    }


class SourcePackManifestTests(unittest.TestCase):
    def test_valid_schema3_manifest(self):
        MODULE.validate(manifest(), contract(), expected_tag="miyorare-sources-v1.2.3")

    def test_schema2_is_not_silently_redefined(self):
        data = manifest()
        data["schema"] = 2
        with self.assertRaises(MODULE.ManifestError):
            MODULE.validate(data, contract())

    def test_beta_channel_is_rejected_for_stable_manifest(self):
        data = manifest()
        data["compatibility"]["channel"] = "beta"
        with self.assertRaises(MODULE.ManifestError):
            MODULE.validate(data, contract())

    def test_epoch_and_tsuki_api_are_contract_bound(self):
        for key, value in (("compatibilityEpoch", 2), ("tsukiApi", "2.0.0")):
            data = manifest()
            data["compatibility"][key] = value
            with self.assertRaises(MODULE.ManifestError):
                MODULE.validate(data, contract())

    def test_version_range_is_required_and_sane(self):
        data = manifest()
        data["compatibility"]["minMiyorareVersionCode"] = 0
        with self.assertRaises(MODULE.ManifestError):
            MODULE.validate(data, contract())
        data = manifest()
        data["compatibility"]["maxMiyorareVersionCode"] = 74
        with self.assertRaises(MODULE.ManifestError):
            MODULE.validate(data, contract())

    def test_stable_runtime_baseline_is_not_beta(self):
        data = manifest()
        data["runtimeCompatibility"]["branch"] = "beta"
        with self.assertRaises(MODULE.ManifestError):
            MODULE.validate(data, contract())

    def test_required_logical_pack_cannot_be_omitted(self):
        data = manifest()
        data["packs"] = data["packs"][:-1]
        with self.assertRaises(MODULE.ManifestError):
            MODULE.validate(data, contract())

    def test_release_lock_requirement_cannot_be_disabled(self):
        data = manifest()
        data["compatibility"]["releaseLockRequired"] = False
        with self.assertRaises(MODULE.ManifestError):
            MODULE.validate(data, contract())

    def test_legacy_schema3_without_snapshot_remains_auditable_but_not_new_release_valid(self):
        data = manifest()
        data.pop("compatibilitySnapshotId")
        data.pop("compatibilitySnapshot")
        MODULE.validate(data, contract())
        with self.assertRaises(MODULE.ManifestError):
            MODULE.validate(data, contract(), require_compatibility_snapshot=True)

    def test_compatibility_snapshot_is_deterministic_and_fail_closed(self):
        data = manifest()
        expected = data["compatibilitySnapshotId"]
        self.assertEqual(
            expected,
            MODULE.compatibility_snapshot_id(
                CONTRACT_SHA,
                SHA2,
                SHA1,
                FARM_SHA,
                {"uma": SHA2, "gekkoushi": SHA3, "keiyoushi": SHA4},
            ),
        )
        data["compatibilitySnapshot"]["farmCommit"] = "6" * 40
        with self.assertRaises(MODULE.ManifestError):
            MODULE.validate(data, contract())

    def test_generate_binds_real_shard_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = {
                "id": ("miyorare-id", "id", [
                    ("UMA", "miyorare-id", "miyorare-id-uma.jar"),
                    ("GEKKOUSHI", "miyorare-id-gekkoushi", "miyorare-id-gekkoushi.jar"),
                ]),
                "en": ("miyorare-en", "en", [
                    ("UMA", "miyorare-en", "miyorare-en-uma.jar"),
                    ("GEKKOUSHI", "miyorare-en-gekkoushi", "miyorare-en-gekkoushi.jar"),
                ]),
                "global": ("miyorare-global", "all", [
                    ("GEKKOUSHI", "miyorare-global", "miyorare-global-gekkoushi.jar"),
                ]),
            }
            for language, (pack_id, logical_language, shards) in fixtures.items():
                logical_shards = []
                for index, (provider, plugin_id, asset_name) in enumerate(shards, start=1):
                    (root / asset_name).write_bytes((asset_name + "\n").encode())
                    logical_shards.append({
                        "provider": provider,
                        "pluginId": plugin_id,
                        "assetName": asset_name,
                        "sourceCount": index,
                    })
                (root / f"miyorare-{language}-pack.json").write_text(json.dumps({
                    "packId": pack_id,
                    "language": logical_language,
                    "sourceCount": sum(item["sourceCount"] for item in logical_shards),
                    "shards": logical_shards,
                }), encoding="utf-8")

            result = MODULE.generate(
                dist=root,
                version="2.0.0",
                source_commit=SHA1,
                runtime_commit=SHA2,
                runtime_version_code=75,
                tsuki_api="1.0.5",
                compatibility_epoch=1,
                upstreams={"uma": SHA2, "gekkoushi": SHA3, "keiyoushi": SHA4},
                farm_commit=FARM_SHA,
                contract_sha256=CONTRACT_SHA,
                contract=contract(),
            )
            self.assertEqual(3, result["schema"])
            self.assertEqual(SHA2, result["runtimeCompatibility"]["commit"])
            self.assertEqual(75, result["compatibility"]["minMiyorareVersionCode"])
            self.assertEqual(FARM_SHA, result["compatibilitySnapshot"]["farmCommit"])
            self.assertEqual(CONTRACT_SHA, result["compatibilitySnapshot"]["contractSha256"])
            self.assertEqual(64, len(result["compatibilitySnapshotId"]))
            for pack in result["packs"]:
                for shard in pack["shards"]:
                    self.assertEqual(64, len(shard["sha256"]))
                    self.assertGreater(shard["size"], 0)


if __name__ == "__main__":
    unittest.main()
