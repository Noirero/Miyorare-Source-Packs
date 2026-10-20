from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "tools" / "source_lab_c1_id_mapping.py"
spec = importlib.util.spec_from_file_location("source_lab_c1_id_mapping", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def inventory(*sources):
    return {
        "kind": "MIYORARE_SOURCE_INVENTORY",
        "informationalOnly": True,
        "stats": {"allSources": len(sources)},
        "providerSnapshots": {
            "uma": {"commit": "u" * 40},
            "gekkoushi": {"commit": "g" * 40},
            "keiyoushi": {"commit": "k" * 40},
        },
        "sources": list(sources),
    }


def source(cid, language="id", providers=None, attention=False):
    return {
        "canonicalId": cid,
        "displayName": cid.rsplit(":", 1)[-1],
        "language": language,
        "identityConfidence": "explicit",
        "needsAttention": attention,
        "attentionReasons": ["synthetic"] if attention else [],
        "providers": providers or {},
    }


def farm(*sources):
    return {"sources": list(sources)}


def farm_source(cid, providers=None, identities=None, state="ACTIVE"):
    return {
        "canonicalId": cid,
        "displayName": cid.rsplit(":", 1)[-1],
        "language": "id",
        "providers": providers or [],
        "upstreamIdentities": identities or {},
        "compatibilityEnrollment": {"state": state},
    }


def packs(entries=None, include_all=None):
    return {
        "packs": {
            "id": {
                "pluginId": "miyorare-id",
                "language": "id",
                "sources": entries or [],
                "includeAllFrom": include_all or [],
            }
        }
    }


def empty_status():
    return {"providers": {}, "automation": {"candidates": {}}}


class TrackCIdMappingTests(unittest.TestCase):
    def test_provider_neutral_mapping_and_consumer_packaging(self):
        cid = "miyorare:miyorare-id:BACAMI"
        uma = {"file": "src/main/kotlin/tsuki/site/id/Bacami.kt", "sourceName": "BACAMI"}
        gek = {"file": "src/main/kotlin/tsuki/site/id/Bacami.kt", "sourceName": "BACAMI"}
        kei = {"module": "src/id/bacami", "sourceId": 1}
        report = module.build_report(
            inventory(source(cid, providers={"uma": uma, "gekkoushi": gek, "keiyoushi": kei})),
            farm(farm_source(cid, ["uma", "gekkoushi", "keiyoushi"], {"uma": uma, "gekkoushi": gek, "keiyoushi": kei})),
            {"aliases": [{"canonicalId": cid, "language": "id", "official": {"sourceName": "BACAMI"}, "uma": uma, "keiyoushi": kei}]},
            packs(["Bacami.kt"], ["gekkoushi"]),
            {"providers": {}},
            empty_status(),
        )
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(report["authority"]["providerDecision"], "UNDECIDED_PENDING_TRACK_C_CAPABILITY_HEALTH")
        self.assertEqual(report["currentConsumer"]["packagedProviders"], ["uma", "gekkoushi"])
        self.assertEqual(report["summary"]["consumerUmaCuratedResolved"], 1)
        self.assertEqual(report["inventoryProviderCombinationCounts"]["keiyoushi+uma+gekkoushi"], 1)

    def test_missing_curated_uma_path_is_structural_finding(self):
        report = module.build_report(
            inventory(), farm(), {"aliases": []}, packs(["Missing.kt"], ["gekkoushi"]), {"providers": {}}, empty_status()
        )
        self.assertEqual(report["status"], "COMPLETE_WITH_FINDINGS")
        self.assertEqual(report["summary"]["structuralAttentionCount"], 1)
        self.assertEqual(len(report["findings"]["consumerUmaCuratedPathMissingFromInventory"]), 1)

    def test_provider_identity_drift_is_detected(self):
        cid = "miyorare:miyorare-id:X"
        inv_uma = {"file": "src/main/kotlin/tsuki/site/id/X.kt", "sourceName": "X"}
        farm_uma = {"file": "src/main/kotlin/tsuki/site/id/Y.kt", "sourceName": "X"}
        report = module.build_report(
            inventory(source(cid, providers={"uma": inv_uma})),
            farm(farm_source(cid, ["uma"], {"uma": farm_uma})),
            {"aliases": []}, packs(["X.kt"]), {"providers": {}}, empty_status()
        )
        self.assertEqual(len(report["findings"]["providerIdentityDrift"]), 1)
        self.assertEqual(report["status"], "COMPLETE_WITH_FINDINGS")

    def test_inventory_not_yet_enrolled_is_reported_but_not_structural(self):
        cid = "miyorare:inventory-id:NEW"
        uma = {"file": "src/main/kotlin/tsuki/site/id/New.kt", "sourceName": "NEW"}
        report = module.build_report(
            inventory(source(cid, providers={"uma": uma})), farm(), {"aliases": []}, packs(), {"providers": {}}, empty_status()
        )
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(report["findings"]["inventoryCanonicalNotEnrolledInFarm"], [cid])

    def test_en_rows_do_not_enter_id_cohort(self):
        report = module.build_report(
            inventory(source("miyorare:miyorare-en:X", language="en", providers={"uma": {"file": "x", "sourceName": "X"}})),
            farm(), {"aliases": []}, packs(), {"providers": {}}, empty_status()
        )
        self.assertEqual(report["summary"]["inventoryIdSources"], 0)

    def test_duplicate_id_canonical_fails_closed(self):
        cid = "miyorare:miyorare-id:DUP"
        with self.assertRaisesRegex(ValueError, "duplicate inventory ID canonicalId"):
            module.build_report(
                inventory(source(cid), source(cid)), farm(), {"aliases": []}, packs(), {"providers": {}}, empty_status()
            )


if __name__ == "__main__":
    unittest.main()
