#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import source_lab_b4_en_adoption_drift as b4

SHA = {
    "main": "1" * 40,
    "inventory": "2" * 40,
    "farm": "3" * 40,
    "app": "4" * 40,
    "kei": "5" * 40,
    "uma": "6" * 40,
    "gek": "7" * 40,
}


def baseline():
    return {
        "schemaVersion": 1,
        "phase": b4.BASELINE_PHASE,
        "readOnly": True,
        "refs": {
            "sourcePacksAfterBatch3": SHA["main"],
            "sourceInventory": SHA["inventory"],
            "compatibilityFarm": SHA["farm"],
            "miyorareAmain2": SHA["app"],
        },
        "consumer": {"repository": "Noirero/Miyorare", "branch": "Amain2"},
        "batch3Closure": {
            "rows": 33,
            "evidenceBackedRows": 33,
            "routes": dict(b4.EXPECTED_B3_ROUTES),
            "adoptionEligibleRows": 0,
        },
        "adoptionPolicy": {
            "mode": "PASS_ONLY",
            "eligibleRoute": b4.PASS_ADOPTION_ROUTE,
            "allowImplicitReplacement": False,
            "allowReferenceOnlyPromotion": False,
        },
        "existingAutomation": {
            "inventory": ".github/workflows/source-inventory-sync.yml",
            "membership": ".github/workflows/source-lab-sync-farm-membership.yml",
            "runtime": ".github/workflows/source-lab-pending-worker.yml",
            "approval": ".github/workflows/source-lab-approve-ready-sources.yml",
        },
    }


def b3_closure():
    routes = (
        ["PROVEN_UPSTREAM_DEAD"] * 23
        + ["PROVEN_UPSTREAM_MIGRATION"]
        + ["LIVE_ACCESS_BLOCKED"] * 8
        + ["LIVE_DOMAIN_DISPOSITION"]
    )
    return {
        "schemaVersion": 1,
        "phase": b4.B3_PHASE,
        "readOnly": True,
        "summary": {"rows": 33, "evidenceBackedRows": 33, "routes": dict(b4.EXPECTED_B3_ROUTES)},
        "decisions": [
            {"canonicalId": f"miyorare:inventory-en:SRC{index}", "route": route}
            for index, route in enumerate(routes)
        ],
        "safety": {
            "approvesOverlay": False,
            "mutatesAuthority": False,
            "mutatesCanonicalIds": False,
            "mutatesLastKnownGood": False,
            "mutatesRetryHeld": False,
            "promotesProvider": False,
        },
    }


def inventory(extra=None, uma=None):
    sources = [
        {
            "canonicalId": "miyorare:inventory-en:ONE",
            "displayName": "One",
            "language": "en",
            "identityConfidence": "explicit",
            "needsAttention": False,
            "attentionReasons": [],
            "providers": {
                "uma": {
                    "available": True,
                    "file": "src/main/kotlin/tsuki/site/en/One.kt",
                    "sourceName": "ONE",
                }
            },
        }
    ]
    if extra:
        sources.append(extra)
    return {
        "schemaVersion": 1,
        "kind": "MIYORARE_SOURCE_INVENTORY",
        "informationalOnly": True,
        "providerSnapshots": {
            "keiyoushi": {"commit": SHA["kei"]},
            "uma": {"commit": uma or SHA["uma"]},
            "gekkoushi": {"commit": SHA["gek"]},
        },
        "stats": {"allSources": len(sources), "providerMappings": len(sources), "needsAttention": 0},
        "sources": sources,
    }


def farm(uma=None):
    return {
        "schemaVersion": 1,
        "providerBaselines": {
            "keiyoushi": SHA["kei"],
            "uma": uma or SHA["uma"],
            "gekkoushi": SHA["gek"],
        },
        "sources": [
            {
                "canonicalId": "miyorare:inventory-en:ONE",
                "displayName": "One",
                "language": "en",
                "providers": ["uma"],
                "upstreamIdentities": {
                    "uma": {
                        "file": "src/main/kotlin/tsuki/site/en/One.kt",
                        "sourceName": "ONE",
                    }
                },
                "compatibilityEnrollment": {"state": "ACTIVE"},
                "runtimeHealth": "HEALTHY",
            }
        ],
    }


def make_app(root: Path, *, pin="a" * 40, source="One.kt", overlay=False):
    base = root / "extensions/miyorare-sources"
    base.mkdir(parents=True, exist_ok=True)
    (base / "packs.json").write_text(json.dumps({
        "schema": 1,
        "upstream": {"name": "UMA", "repository": "InvalidDavid/UMA", "commit": pin},
        "additionalUpstreams": {
            "gekkoushi": {"name": "Gekkoushi", "repository": "Gekkoushi/plugin-source", "commit": pin}
        },
        "packs": {
            "en": {
                "pluginId": "miyorare-en",
                "language": "en",
                "sources": [source],
                "includeAllFrom": ["gekkoushi"],
            }
        },
    }), encoding="utf-8")
    (base / "multi-upstream.json").write_text(json.dumps({
        "schema": 1,
        "upstreams": {"uma": {"commit": pin}},
        "aliases": [
            {
                "canonicalId": "miyorare:miyorare-en:ONE",
                "language": "en",
                "verifiedDomain": "one.example",
                "official": {"pack": "en", "pluginId": "miyorare-en", "sourceName": "ONE"},
                "uma": {
                    "file": "src/main/kotlin/tsuki/site/en/One.kt",
                    "sourceName": "ONE",
                },
            }
        ],
    }), encoding="utf-8")
    if overlay:
        target = base / "overlays/gekkoushi/en/One.kt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("// overlay\n", encoding="utf-8")


class Batch4Tests(unittest.TestCase):
    def build(self, *, inv0=None, inv1=None, farm0=None, farm1=None, app1_kwargs=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            app0 = tmp / "app0"
            app1 = tmp / "app1"
            make_app(app0)
            make_app(app1, **(app1_kwargs or {}))
            return b4.build_report(
                baseline(),
                b3_closure(),
                inv0 or inventory(),
                inv1 or inventory(),
                farm0 or farm(),
                farm1 or farm(),
                app0,
                app1,
                {
                    "sourceInventory": SHA["inventory"],
                    "compatibilityFarm": SHA["farm"],
                    "miyorareAmain2": SHA["app"],
                },
            )

    def test_clean_baseline_closes_track_b_without_adoption(self):
        report = self.build()
        self.assertEqual("TRACK_B_CLOSED_BASELINE_CLEAN", report["status"])
        self.assertTrue(report["trackBClosed"])
        self.assertEqual(0, report["adoption"]["eligibleRows"])
        self.assertFalse(report["adoption"]["adoptionPerformed"])
        self.assertFalse(report["handoff"]["required"])
        self.assertFalse(any(report["safety"].values()))

    def test_consumer_commit_pin_only_is_not_semantic_drift(self):
        report = self.build(app1_kwargs={"pin": "b" * 40})
        self.assertFalse(report["drift"]["miyorareAmain2EnSemanticDrift"])
        self.assertFalse(report["handoff"]["required"])

    def test_upstream_snapshot_change_requires_handoff(self):
        report = self.build(inv1=inventory(uma="8" * 40))
        self.assertTrue(report["drift"]["upstreamProviderCommitDrift"])
        self.assertTrue(report["handoff"]["required"])
        self.assertEqual("EXISTING_SOURCE_LAB_PIPELINE", report["handoff"]["mode"])

    def test_inventory_identity_change_requires_handoff(self):
        extra = {
            "canonicalId": "miyorare:inventory-en:TWO",
            "language": "en",
            "providers": {
                "gekkoushi": {
                    "available": True,
                    "file": "src/main/kotlin/tsuki/site/en/Two.kt",
                    "sourceName": "TWO",
                }
            },
        }
        report = self.build(inv1=inventory(extra=extra))
        self.assertTrue(report["drift"]["inventoryEnSemanticDrift"])
        self.assertEqual(["miyorare:inventory-en:TWO"], report["drift"]["inventoryChangedCanonicalIds"])

    def test_farm_provider_baseline_change_requires_handoff(self):
        report = self.build(farm1=farm(uma="9" * 40))
        self.assertTrue(report["drift"]["farmProviderBaselineDrift"])
        self.assertTrue(report["handoff"]["required"])

    def test_consumer_membership_or_overlay_change_requires_handoff(self):
        changed = self.build(app1_kwargs={"source": "Two.kt"})
        self.assertTrue(changed["drift"]["miyorareAmain2EnSemanticDrift"])
        overlay = self.build(app1_kwargs={"overlay": True})
        self.assertTrue(overlay["drift"]["miyorareAmain2EnSemanticDrift"])

    def test_lifecycle_only_farm_change_is_ignored(self):
        changed = farm()
        changed["sources"][0]["compatibilityEnrollment"]["state"] = "HELD"
        changed["sources"][0]["runtimeHealth"] = "BLOCKED"
        report = self.build(farm1=changed)
        self.assertFalse(report["drift"]["farmEnSemanticDrift"])

    def test_non_pass_b3_route_cannot_be_silently_adopted(self):
        closure = b3_closure()
        closure["decisions"][0]["route"] = b4.PASS_ADOPTION_ROUTE
        with self.assertRaises(ValueError):
            b4.validate_b3_closure(closure, baseline())


if __name__ == "__main__":
    unittest.main()
