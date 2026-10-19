import copy
import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "source_lab_b2_capability_health.py"
spec = importlib.util.spec_from_file_location("source_lab_b2_capability_health", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def farm_source(cid, providers, identities, *, status="PENDING"):
    commits = {provider: f"commit-{provider}" for provider in providers}
    return {
        "canonicalId": cid,
        "displayName": cid.rsplit(":", 1)[-1],
        "language": "en",
        "providers": providers,
        "upstreamIdentities": identities,
        "compatibilityBaseline": {"status": status, "capabilities": ["browse", "details", "chapters", "content"]},
        "compatibilityEnrollment": {"state": "PENDING"},
        "authType": "NO_AUTH",
        "adapterFamily": "test",
        "contentProfile": "manga",
        "currentVersion": commits,
        "lastKnownGood": copy.deepcopy(commits),
    }


def inventory_source(cid, providers):
    return {"canonicalId": cid, "displayName": cid.rsplit(":", 1)[-1], "language": "en", "providers": providers}


class B2DecisionTests(unittest.TestCase):
    def make_inputs(self):
        missing = "miyorare:inventory-en:MISSING"
        refgap = "miyorare:inventory-en:REFGAP"
        drift = "miyorare:inventory-en:DRIFT"
        b1 = {
            "phase": "TRACK_B_BATCH_1_EN_AUDIT_MAPPING",
            "readOnly": True,
            "summary": {"structuralAttentionCount": 3},
            "provenance": {"inventoryCommit": "i", "foundationCommit": "f", "miyorareCommit": "m"},
            "findings": {
                "farmCanonicalMissingFromInventory": [missing],
                "farmProviderNotDiscovered": [{"canonicalId": refgap, "provider": "keiyoushi"}],
                "providerIdentityDrift": [{
                    "canonicalId": drift,
                    "provider": "keiyoushi",
                    "farmIdentity": "module:src/en/drift|sourceId:111",
                    "inventoryIdentity": "module:src/en/drift|sourceId:222",
                }],
                "inventoryCanonicalNotEnrolledInFarm": ["miyorare:inventory-en:DISCOVERYONLY"],
                "discoveredProviderNotEnrolled": [{"canonicalId": "miyorare:inventory-en:DISCOVERYONLY", "provider": "uma"}],
                "referenceOnlyKeiyoushi": [],
            },
        }
        inventory = {
            "kind": "MIYORARE_SOURCE_INVENTORY",
            "informationalOnly": True,
            "sources": [
                inventory_source(refgap, {"uma": {"file": "src/Ref.kt", "sourceName": "REF"}}),
                inventory_source(drift, {"keiyoushi": {"module": "src/en/drift", "sourceId": 222, "sourceName": "Drift"}}),
            ],
        }
        farm = {
            "schemaVersion": 1,
            "sources": [
                farm_source(missing, ["gekkoushi"], {"gekkoushi": {"file": "src/Missing.kt", "sourceName": "MISSING"}}),
                farm_source(refgap, ["uma", "keiyoushi"], {
                    "uma": {"file": "src/Ref.kt", "sourceName": "REF"},
                    "keiyoushi": {"module": "src/en/ref", "sourceId": 9, "sourceName": "Ref"},
                }),
                farm_source(drift, ["keiyoushi"], {"keiyoushi": {"module": "src/en/drift", "sourceId": 111, "sourceName": "Drift"}}),
            ],
        }
        health = {
            "schema": 1,
            "sources": {
                "gekkoushi:en:MISSING": {
                    "sourceKey": "gekkoushi:en:MISSING", "provider": "gekkoushi", "pack": "en",
                    "sourceId": "MISSING", "sourceName": "Missing", "path": "src/Missing.kt", "runtimeHealth": "HEALTHY", "activeCommit": "commit-gekkoushi",
                },
                "uma:en:REF": {
                    "sourceKey": "uma:en:REF", "provider": "uma", "pack": "en",
                    "sourceId": "REF", "sourceName": "Ref", "path": "src/Ref.kt", "runtimeHealth": "HEALTHY", "activeCommit": "commit-uma",
                },
            },
        }
        return b1, inventory, farm, health

    def test_complete_structural_cohort_and_excludes_informational_observations(self):
        b1, inventory, farm, health = self.make_inputs()
        report = mod.build_report(b1, inventory, farm, health)
        self.assertEqual(3, report["summary"]["decisionRows"])
        ids = {row["canonicalId"] for row in report["decisions"]}
        self.assertNotIn("miyorare:inventory-en:DISCOVERYONLY", ids)
        self.assertEqual(1, report["summary"]["informationalB1ObservationsExcludedFrom38"]["inventoryCanonicalNotEnrolledInFarm"])

    def test_reference_numeric_id_drift_is_deferred_to_track_c(self):
        b1, inventory, farm, health = self.make_inputs()
        report = mod.build_report(b1, inventory, farm, health)
        row = next(row for row in report["decisions"] if row["canonicalId"].endswith(":DRIFT"))
        self.assertEqual("DEFER_TRACK_C_REFERENCE_ID_RECONCILIATION", row["decision"]["decision"])
        self.assertEqual("TRACK_C", row["decision"]["nextPhase"])
        self.assertTrue(row["safety"]["preserveCanonicalId"])
        self.assertFalse(row["safety"]["adoptKeiyoushiAsPrimary"])

    def test_healthy_primary_makes_keiyoushi_gap_nonblocking_for_track_b(self):
        b1, inventory, farm, health = self.make_inputs()
        report = mod.build_report(b1, inventory, farm, health)
        row = next(row for row in report["decisions"] if row["canonicalId"].endswith(":REFGAP"))
        self.assertEqual("UMA_HEALTHY_PREFERRED", row["primaryDecision"]["preference"])
        self.assertEqual("NO_TRACK_B_REPAIR_REFERENCE_ONLY_GAP", row["decision"]["decision"])
        self.assertEqual("TRACK_D", row["decision"]["nextPhase"])

    def test_missing_inventory_with_healthy_primary_preserves_lkg_and_routes_batch3(self):
        b1, inventory, farm, health = self.make_inputs()
        report = mod.build_report(b1, inventory, farm, health)
        row = next(row for row in report["decisions"] if row["canonicalId"].endswith(":MISSING"))
        self.assertEqual("HEALTHY", row["primaryDecision"]["aggregateHealth"])
        self.assertEqual("B3_RECONCILE_DISCOVERY_WITH_HEALTHY_PRIMARY_LKG", row["decision"]["decision"])
        self.assertTrue(row["safety"]["preserveLastKnownGood"])
        self.assertFalse(row["safety"]["mutateRetryHeld"])

    def test_presence_without_health_evidence_remains_unknown(self):
        b1, inventory, farm, health = self.make_inputs()
        health["sources"].pop("gekkoushi:en:MISSING")
        report = mod.build_report(b1, inventory, farm, health)
        row = next(row for row in report["decisions"] if row["canonicalId"].endswith(":MISSING"))
        self.assertEqual("UNKNOWN", row["providers"]["gekkoushi"]["health"]["health"])
        self.assertEqual("B3_RUNTIME_AND_DISCOVERY_VALIDATION_REQUIRED", row["decision"]["decision"])

    def test_health_from_different_provider_commit_is_not_promoted_to_current_health(self):
        b1, inventory, farm, health = self.make_inputs()
        health["sources"]["uma:en:REF"]["activeCommit"] = "stale-uma-commit"
        report = mod.build_report(b1, inventory, farm, health)
        row = next(row for row in report["decisions"] if row["canonicalId"].endswith(":REFGAP"))
        evidence = row["providers"]["uma"]["health"]
        self.assertEqual("UNKNOWN", evidence["health"])
        self.assertEqual("HEALTHY", evidence["observedRuntimeHealth"])
        self.assertEqual("STALE_HEALTH_COMMIT_MISMATCH", evidence["match"])
        self.assertEqual("B3_VALIDATE_PRIMARY_BEFORE_IGNORING_REFERENCE_GAP", row["decision"]["decision"])

    def test_inputs_are_not_mutated(self):
        inputs = self.make_inputs()
        before = copy.deepcopy(inputs)
        mod.build_report(*inputs)
        self.assertEqual(before, inputs)

    def test_structural_count_mismatch_fails_closed(self):
        b1, inventory, farm, health = self.make_inputs()
        b1["summary"]["structuralAttentionCount"] = 4
        with self.assertRaisesRegex(ValueError, "structural cohort mismatch"):
            mod.build_report(b1, inventory, farm, health)

    def test_ambiguous_health_identity_does_not_guess(self):
        b1, inventory, farm, health = self.make_inputs()
        health["sources"]["gekkoushi:en:MISSING2"] = dict(
            health["sources"]["gekkoushi:en:MISSING"], sourceKey="gekkoushi:en:MISSING2"
        )
        report = mod.build_report(b1, inventory, farm, health)
        row = next(row for row in report["decisions"] if row["canonicalId"].endswith(":MISSING"))
        self.assertEqual("UNKNOWN", row["providers"]["gekkoushi"]["health"]["health"])
        self.assertEqual("AMBIGUOUS_IDENTITY_MATCH", row["providers"]["gekkoushi"]["health"]["match"])


if __name__ == "__main__":
    unittest.main()
