import copy
import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "source_lab_c2_id_capability_health.py"
spec = importlib.util.spec_from_file_location("source_lab_c2_id_capability_health", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

I = "inventory-sha"
F = "foundation-sha"
M = "miyorare-sha"


def inv(cid, providers):
    return {"canonicalId": cid, "displayName": cid.rsplit(":", 1)[-1], "language": "id", "providers": providers}


def farm(cid, providers, identities, *, health_status="PENDING"):
    commits = {provider: f"commit-{provider}" for provider in providers}
    return {
        "canonicalId": cid,
        "displayName": cid.rsplit(":", 1)[-1],
        "language": "id",
        "providers": providers,
        "upstreamIdentities": identities,
        "compatibilityBaseline": {"status": health_status, "capabilities": ["browse", "details", "chapters", "content"]},
        "compatibilityEnrollment": {"state": "ACTIVE"},
        "authType": "NO_AUTH",
        "adapterFamily": "test",
        "contentProfile": "manga",
        "currentVersion": commits,
        "lastKnownGood": copy.deepcopy(commits),
    }


def health(provider, sid, path, *, runtime="HEALTHY", commit=None, name=None):
    return {
        "sourceKey": f"{provider}:id:{sid}",
        "provider": provider,
        "pack": "id",
        "sourceId": sid,
        "sourceName": name or sid,
        "path": path,
        "runtimeHealth": runtime,
        "activeCommit": commit or f"commit-{provider}",
    }


class C2DecisionTests(unittest.TestCase):
    def make_inputs(self):
        missing = "miyorare:inventory-id:MISSING"
        drift = "miyorare:inventory-id:DRIFT"
        new = "miyorare:inventory-id:NEW"
        alt = "miyorare:inventory-id:ALT"
        uncovered = "miyorare:inventory-id:UNCOVERED"
        healthy_uma = "miyorare:inventory-id:HEALTHYUMA"

        c1 = {
            "phase": "TRACK_C_BATCH_1_ID_AUDIT_MAPPING",
            "status": "COMPLETE_WITH_FINDINGS",
            "readOnly": True,
            "language": "id",
            "provenance": {"inventoryCommit": I, "foundationCommit": F, "miyorareCommit": M},
            "currentConsumer": {
                "pluginId": "miyorare-id",
                "gekkoushiMode": "INCLUDE_ALL_FROM",
                "packagedProviders": ["uma", "gekkoushi"],
                "umaCuratedEntries": ["Curated.kt"],
            },
            "summary": {"structuralAttentionCount": 2},
            "findings": {
                "farmCanonicalMissingFromInventory": [missing],
                "providerIdentityDrift": [{
                    "canonicalId": drift,
                    "provider": "keiyoushi",
                    "farmIdentity": "module:src/id/drift|sourceId:111",
                    "inventoryIdentity": "module:src/id/drift|sourceId:222",
                }],
                "inventoryCanonicalNotEnrolledInFarm": [new],
                "discoveredProviderNotEnrolled": [
                    {"canonicalId": alt, "provider": "keiyoushi"},
                    {"canonicalId": uncovered, "provider": "uma"},
                ],
                "inventoryUmaNotCuratedByConsumer": [
                    "src/main/kotlin/tsuki/site/id/Alt.kt",
                    "src/main/kotlin/tsuki/site/id/Uncovered.kt",
                    "src/main/kotlin/tsuki/site/id/HealthyUma.kt",
                ],
            },
        }
        inventory = {
            "kind": "MIYORARE_SOURCE_INVENTORY",
            "informationalOnly": True,
            "sources": [
                inv(drift, {"keiyoushi": {"module": "src/id/drift", "sourceId": 222, "sourceName": "Drift"}}),
                inv(new, {"uma": {"file": "src/main/kotlin/tsuki/site/id/New.kt", "sourceName": "New"}}),
                inv(alt, {
                    "gekkoushi": {"file": "src/id/Alt.kt", "sourceName": "Alt"},
                    "uma": {"file": "src/main/kotlin/tsuki/site/id/Alt.kt", "sourceName": "Alt"},
                    "keiyoushi": {"module": "src/id/alt", "sourceId": 90, "sourceName": "Alt"},
                }),
                inv(uncovered, {"uma": {"file": "src/main/kotlin/tsuki/site/id/Uncovered.kt", "sourceName": "Uncovered"}}),
                inv(healthy_uma, {"uma": {"file": "src/main/kotlin/tsuki/site/id/HealthyUma.kt", "sourceName": "HealthyUma"}}),
            ],
        }
        farm_registry = {
            "schemaVersion": 1,
            "sources": [
                farm(missing, ["gekkoushi"], {"gekkoushi": {"file": "src/id/Missing.kt", "sourceName": "Missing"}}),
                farm(drift, ["keiyoushi"], {"keiyoushi": {"module": "src/id/drift", "sourceId": 111, "sourceName": "Drift"}}),
                farm(alt, ["gekkoushi"], {"gekkoushi": {"file": "src/id/Alt.kt", "sourceName": "Alt"}}),
                farm(uncovered, ["gekkoushi"], {"gekkoushi": {"file": "src/id/UncoveredG.kt", "sourceName": "Uncovered"}}),
                farm(healthy_uma, ["uma"], {"uma": {"file": "src/main/kotlin/tsuki/site/id/HealthyUma.kt", "sourceName": "HealthyUma"}}),
            ],
        }
        source_health = {
            "schema": 1,
            "sources": {
                "g-missing": health("gekkoushi", "Missing", "src/id/Missing.kt"),
                "g-alt": health("gekkoushi", "Alt", "src/id/Alt.kt"),
                "u-healthy": health("uma", "HealthyUma", "src/main/kotlin/tsuki/site/id/HealthyUma.kt"),
            },
        }
        return c1, inventory, farm_registry, source_health

    def build(self):
        return mod.build_report(*self.make_inputs(), inventory_commit=I, foundation_commit=F, miyorare_commit=M)

    def test_covers_every_c1_finding_row(self):
        report = self.build()
        self.assertEqual(8, report["summary"]["findingRows"])
        self.assertEqual(2, report["summary"]["structuralAttentionCount"])
        self.assertEqual(8, len(report["findingDecisions"]))

    def test_id_migration_preserves_canonical_and_routes_c3(self):
        report = self.build()
        row = next(row for row in report["findingDecisions"] if row["finding"]["type"] == "providerIdentityDrift")
        self.assertEqual("C3_VERIFY_REFERENCE_IDENTITY_MIGRATION", row["decision"]["decision"])
        self.assertEqual("TRACK_C_BATCH_3", row["decision"]["nextPhase"])
        self.assertTrue(row["safety"]["preserveCanonicalId"])
        self.assertFalse(row["safety"]["mutateAuthority"])

    def test_missing_inventory_with_healthy_lkg_routes_c3(self):
        report = self.build()
        row = next(row for row in report["findingDecisions"] if row["canonicalId"].endswith(":MISSING"))
        self.assertEqual("HEALTHY", row["consumerCoverageHealth"])
        self.assertEqual("C3_RECONCILE_DISCOVERY_WITH_HEALTHY_LKG", row["decision"]["decision"])

    def test_reference_only_new_provider_is_not_adopted_when_coverage_exists(self):
        report = self.build()
        row = next(row for row in report["findingDecisions"] if row["canonicalId"].endswith(":ALT") and row["finding"]["type"] == "discoveredProviderNotEnrolled")
        self.assertEqual("NO_C3_REFERENCE_ONLY_PROVIDER_DISCOVERY", row["decision"]["decision"])
        self.assertEqual("TRACK_C_BATCH_4", row["decision"]["nextPhase"])
        self.assertFalse(row["safety"]["autoAdoptProvider"])

    def test_uma_not_curated_with_gekkoushi_coverage_is_not_auto_adopted(self):
        report = self.build()
        row = next(row for row in report["findingDecisions"] if row["canonicalId"].endswith(":ALT") and row["finding"]["type"] == "inventoryUmaNotCuratedByConsumer")
        self.assertEqual("NO_C3_UMA_NOT_CURATED_REDUNDANT_COVERAGE", row["decision"]["decision"])
        self.assertEqual("TRACK_C_BATCH_4", row["decision"]["nextPhase"])

    def test_healthy_enrolled_uncurated_uma_becomes_c4_candidate_not_auto_adoption(self):
        report = self.build()
        row = next(row for row in report["findingDecisions"] if row["canonicalId"].endswith(":HEALTHYUMA"))
        self.assertEqual("C4_ADOPTION_CANDIDATE_NO_AUTO_ADOPTION", row["decision"]["decision"])
        self.assertEqual("TRACK_C_BATCH_4", row["decision"]["nextPhase"])

    def test_unenrolled_and_uncovered_candidate_routes_c3(self):
        report = self.build()
        row = next(row for row in report["findingDecisions"] if row["canonicalId"].endswith(":NEW"))
        self.assertEqual("C3_VALIDATE_UNENROLLED_CANDIDATE_BEFORE_ADOPTION", row["decision"]["decision"])

    def test_health_on_stale_commit_is_not_promoted(self):
        c1, inventory, farm_registry, source_health = self.make_inputs()
        source_health["sources"]["g-missing"]["activeCommit"] = "stale"
        report = mod.build_report(c1, inventory, farm_registry, source_health, inventory_commit=I, foundation_commit=F, miyorare_commit=M)
        assessment = next(row for row in report["sourceAssessments"] if row["canonicalId"].endswith(":MISSING"))
        evidence = assessment["providers"]["gekkoushi"]["health"]
        self.assertEqual("UNKNOWN", evidence["health"])
        self.assertEqual("STALE_HEALTH_COMMIT_MISMATCH", evidence["match"])

    def test_c1_provenance_mismatch_fails_closed(self):
        c1, inventory, farm_registry, source_health = self.make_inputs()
        with self.assertRaisesRegex(ValueError, "C1 provenance mismatch"):
            mod.build_report(c1, inventory, farm_registry, source_health, inventory_commit="wrong", foundation_commit=F, miyorare_commit=M)

    def test_inputs_are_not_mutated(self):
        inputs = self.make_inputs()
        before = copy.deepcopy(inputs)
        mod.build_report(*inputs, inventory_commit=I, foundation_commit=F, miyorare_commit=M)
        self.assertEqual(before, inputs)

    def test_ambiguous_health_identity_fails_to_unknown(self):
        c1, inventory, farm_registry, source_health = self.make_inputs()
        source_health["sources"]["g-missing-2"] = dict(source_health["sources"]["g-missing"], sourceKey="g-missing-2")
        report = mod.build_report(c1, inventory, farm_registry, source_health, inventory_commit=I, foundation_commit=F, miyorare_commit=M)
        assessment = next(row for row in report["sourceAssessments"] if row["canonicalId"].endswith(":MISSING"))
        self.assertEqual("UNKNOWN", assessment["providers"]["gekkoushi"]["health"]["health"])
        self.assertEqual("AMBIGUOUS_IDENTITY_MATCH", assessment["providers"]["gekkoushi"]["health"]["match"])


if __name__ == "__main__":
    unittest.main()
