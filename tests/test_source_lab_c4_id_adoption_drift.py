from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "source_lab_c4_id_adoption_drift.py"
SPEC = importlib.util.spec_from_file_location("c4", MODULE_PATH)
c4 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(c4)
BASELINE_PATH = Path(__file__).resolve().parents[1] / "compatibility/evidence/track-c-batch4-id-baseline.json"


def baseline():
    return json.loads(BASELINE_PATH.read_text())


def fake_c2():
    b = baseline()
    decisions = []
    def add(cid, decision, kind, provider):
        decisions.append({
            "canonicalId": cid,
            "consumerCoverageHealth": "UNKNOWN",
            "consumerCoverageProviders": ["gekkoushi"],
            "finding": {"canonicalId": cid, "type": kind, "detail": {"provider": provider}},
            "decision": {"decision": decision, "nextPhase": "TRACK_C_BATCH_4", "reason": "test"},
            "safety": {"autoAdoptProvider": False, "mutateAuthority": False, "mutateRetryHeld": False, "preserveCanonicalId": True, "preserveLastKnownGood": True},
        })
    for cid in ("KOMBATCH", "LIANSCANS", "LUMOSKOMIK"):
        add(f"miyorare:inventory-id:{cid}", "NO_C3_REFERENCE_ONLY_PROVIDER_DISCOVERY", "discoveredProviderNotEnrolled", "keiyoushi")
    for cid in ("MANHWADESU", "MIKOROKU"):
        add(f"miyorare:inventory-id:{cid}", "NO_C3_REDUNDANT_PROVIDER_DISCOVERY", "discoveredProviderNotEnrolled", "uma")
    for cid in ("MANGAPLUSINDONESIAN", "WEBTOONSINDONESIA", "MIKOROKU", "MANHWADESU"):
        add(f"miyorare:inventory-id:{cid}", "NO_C3_UMA_NOT_CURATED_REDUNDANT_COVERAGE", "inventoryUmaNotCuratedByConsumer", "uma")
    return {
        "phase": c4.C2_PHASE,
        "language": "id",
        "readOnly": True,
        "provenance": {
            "inventoryCommit": b["refs"]["sourceInventory"],
            "foundationCommit": b["refs"]["compatibilityFarm"],
            "miyorareCommit": b["refs"]["miyorareAmain2"],
            "controlCommit": b["artifacts"]["batch2"]["headSha"],
        },
        "summary": {"c4FindingRows": 9},
        "findingDecisions": decisions,
    }


def c3_row(cid, decision, next_action, provider=None, runtime_state=None):
    row = {"canonicalId": f"miyorare:inventory-id:{cid}", "decision": decision, "nextAction": next_action}
    if provider is not None:
        row["provider"] = provider
    if runtime_state is not None:
        row["runtimeState"] = runtime_state
    return row


def fake_c3():
    rows = [
        c3_row("DAILYSUKA", "REFERENCE_REMOVED_UPSTREAM", "C4_REVIEW_STALE_LKG_AND_DEPRECATION"),
        c3_row("IKIRU", "REFERENCE_SOURCE_ID_MIGRATION_CONFIRMED", "C4_RECONCILE_REFERENCE_IDENTITY_WITHOUT_CANONICAL_ID_CHANGE"),
        c3_row("LUMOSKOMIK", "CONSUMED_GEKKOUSHI_RUNTIME_NOT_VALIDATED", "C3_REMEDIATION_REQUIRED", "gekkoushi", "CANDIDATE_NOT_VALIDATED"),
        c3_row("MANGABALLINDONESIAN", "UNCURATED_UMA_RUNTIME_NOT_VALIDATED", "C3_REMEDIATION_REQUIRED", "uma", "CANDIDATE_NOT_VALIDATED"),
        c3_row("MIKOROKU", "REFERENCE_SOURCE_ID_MIGRATION_CONFIRMED", "C4_RECONCILE_REFERENCE_IDENTITY_WITHOUT_CANONICAL_ID_CHANGE"),
        c3_row("PORNHWA18", "REFERENCE_MOVED_OUT_OF_ID_SCOPE", "C4_REVIEW_STALE_ID_FARM_REFERENCE"),
        c3_row("SOFTKOMIK", "UNCURATED_UMA_RUNTIME_NOT_VALIDATED", "C3_REMEDIATION_REQUIRED", "uma", "CANDIDATE_NOT_VALIDATED"),
        c3_row("THRIVEMOE", "UNENROLLED_UMA_RUNTIME_VALIDATED", "C4_CONSIDER_SOURCE_SCOPED_ENROLLMENT_THEN_ADOPTION", "uma", "CANDIDATE_PASS_LKG_NOT_PASSING_OR_ABSENT"),
    ]
    return {
        "phase": c4.C3_PHASE,
        "language": "id",
        "readOnly": True,
        "summary": {
            "canonicalSources": 8,
            "c2FindingRowsCovered": 9,
            "remediationRequired": 3,
            "decisions": baseline()["batch3Boundary"]["decisions"],
        },
        "decisions": rows,
        "safetyBoundary": {
            "autoAdoptProvider": False,
            "mutateCanonicalId": False,
            "mutateConsumerPackaging": False,
            "mutateFarmAuthority": False,
            "mutateLastKnownGood": False,
            "mutateRetryHeld": False,
        },
    }


def inventory():
    sha = "1" * 40
    return {
        "schemaVersion": 1,
        "kind": "MIYORARE_SOURCE_INVENTORY",
        "informationalOnly": True,
        "providerSnapshots": {provider: {"commit": sha} for provider in c4.PROVIDERS},
        "sources": [
            {"canonicalId": "miyorare:inventory-id:A", "language": "id", "providers": {"uma": {"file": "src/A.kt", "sourceName": "A"}}},
            {"canonicalId": "miyorare:inventory-en:X", "language": "en", "providers": {"uma": {"file": "src/X.kt", "sourceName": "X"}}},
        ],
    }


def farm():
    sha = "2" * 40
    return {
        "schemaVersion": 1,
        "providerBaselines": {provider: sha for provider in c4.PROVIDERS},
        "sources": [
            {"canonicalId": "miyorare:inventory-id:A", "language": "id", "providers": ["uma"], "upstreamIdentities": {"uma": {"file": "src/A.kt", "sourceName": "A"}}},
        ],
    }


def write_consumer(root: Path, *, extra_source=False):
    base = root / "extensions/miyorare-sources"
    base.mkdir(parents=True)
    sources = ["uma:src/A.kt"]
    if extra_source:
        sources.append("uma:src/B.kt")
    (base / "packs.json").write_text(json.dumps({"schema": 1, "packs": {"id": {"sources": sources, "includeAllFrom": ["gekkoushi"]}}}))
    (base / "multi-upstream.json").write_text(json.dumps({"schema": 1, "aliases": [{
        "canonicalId": "miyorare:inventory-id:A", "language": "id", "verifiedDomain": "a.example",
        "uma": {"file": "src/A.kt", "sourceName": "A"}
    }]}))


class C4Tests(unittest.TestCase):
    def test_validate_baseline(self):
        c4.validate_baseline(baseline())

    def test_c2_exact_direct_c4_cohort_required(self):
        data = fake_c2()
        data["findingDecisions"].pop()
        with self.assertRaises(ValueError):
            c4.validate_c2(data, baseline())

    def test_c3_pass_only_candidate_requires_runtime_proof(self):
        data = fake_c3()
        row = next(row for row in data["decisions"] if row["canonicalId"].endswith(":THRIVEMOE"))
        row["runtimeState"] = "CANDIDATE_NOT_VALIDATED"
        with self.assertRaises(ValueError):
            c4.validate_c3(data, baseline())

    def test_build_report_keeps_c4_read_only_and_c3_remediation_open(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            left, right = root / "left", root / "right"
            write_consumer(left)
            write_consumer(right)
            report = c4.build_report(
                baseline(), fake_c2(), fake_c3(), inventory(), inventory(), farm(), farm(), left, right,
                {"sourceInventory": "3" * 40, "compatibilityFarm": "4" * 40, "miyorareAmain2": "5" * 40},
            )
            self.assertEqual("TRACK_C_C4_COMPLETE_WITH_C3_REMEDIATION", report["status"])
            self.assertFalse(report["trackCClosed"])
            self.assertEqual(14, report["c4"]["findingRows"])
            self.assertEqual(11, report["c4"]["canonicalSources"])
            self.assertEqual(["miyorare:inventory-id:THRIVEMOE"], report["adoption"]["canonicalIds"])
            self.assertFalse(report["adoption"]["adoptionPerformed"])
            self.assertEqual(3, report["remediation"]["remainingRows"])
            self.assertFalse(any(report["safety"].values()))
            self.assertFalse(report["handoff"]["driftRequired"])

    def test_inventory_semantic_drift_surfaces_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            left, right = root / "left", root / "right"
            write_consumer(left)
            write_consumer(right)
            changed = copy.deepcopy(inventory())
            changed["sources"][0]["providers"]["uma"]["sourceName"] = "A2"
            report = c4.build_report(
                baseline(), fake_c2(), fake_c3(), inventory(), changed, farm(), farm(), left, right,
                {"sourceInventory": "3" * 40, "compatibilityFarm": "4" * 40, "miyorareAmain2": "5" * 40},
            )
            self.assertEqual("TRACK_C_C4_COMPLETE_DRIFT_HANDOFF_REQUIRED", report["status"])
            self.assertTrue(report["drift"]["inventoryIdSemanticDrift"])
            self.assertEqual(["miyorare:inventory-id:A"], report["drift"]["inventoryChangedCanonicalIds"])
            self.assertTrue(report["handoff"]["driftRequired"])

    def test_consumer_semantic_drift_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            left, right = root / "left", root / "right"
            write_consumer(left)
            write_consumer(right, extra_source=True)
            report = c4.build_report(
                baseline(), fake_c2(), fake_c3(), inventory(), inventory(), farm(), farm(), left, right,
                {"sourceInventory": "3" * 40, "compatibilityFarm": "4" * 40, "miyorareAmain2": "5" * 40},
            )
            self.assertTrue(report["drift"]["miyorareAmain2IdSemanticDrift"])

    def test_decision_rows_preserve_overlapping_mikoroku_evidence(self):
        rows = c4.c4_decisions(c4.validate_c2(fake_c2(), baseline()), c4.validate_c3(fake_c3(), baseline())[0])
        mikoroku = next(row for row in rows if row["canonicalId"].endswith(":MIKOROKU"))
        actions = {item["action"] for item in mikoroku["actions"]}
        self.assertEqual({
            "REDUNDANT_PROVIDER_DRIFT_WATCH",
            "REDUNDANT_UMA_NONCURATION_DRIFT_WATCH",
            "REFERENCE_IDENTITY_RECONCILIATION_REVIEW",
        }, actions)


if __name__ == "__main__":
    unittest.main()
