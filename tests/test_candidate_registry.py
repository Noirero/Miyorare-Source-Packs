import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("candidate_registry", ROOT / "tools" / "candidate_registry.py")
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

K = "1" * 40
U = "2" * 40
U2 = "3" * 40
G = "4" * 40


def base_registry():
    return {
        "schemaVersion": 1,
        "providerBaselines": {"keiyoushi": K, "uma": U, "gekkoushi": G},
        "sources": [
            {
                "canonicalId": "miyorare:test:SOURCE",
                "providers": ["uma", "keiyoushi"],
                "currentVersion": {"uma": U, "keiyoushi": K},
                "lastKnownGood": {"uma": U, "keiyoushi": K},
                "updateState": "PROMOTED",
                "approvalState": "NOT_READY",
            }
        ],
    }


def handoff(**overrides):
    value = {
        "schemaVersion": 1,
        "maintenanceMode": "APPROVE_ONLY",
        "state": "CANDIDATE",
        "approvalState": "NOT_READY",
        "publishEligible": False,
        "registryMutationAllowed": False,
        "releaseDispatchAllowed": False,
        "plan": {
            "providers": {
                "keiyoushi": {"lastKnownGood": K, "candidate": K, "changed": False},
                "uma": {"lastKnownGood": U, "candidate": U2, "changed": True},
                "gekkoushi": {"lastKnownGood": G, "candidate": G, "changed": False},
            }
        },
        "validationResults": {
            "keiyoushi": "skipped",
            "uma": "success",
            "gekkoushiOverlayGuard": "skipped",
            "gekkoushi": "skipped",
            "integration": "success",
        },
    }
    value.update(overrides)
    return value


class CandidateRegistryTests(unittest.TestCase):
    def test_candidate_registry_moves_only_ephemeral_current_version(self):
        output = M.build_candidate_registry(base_registry(), handoff())
        self.assertEqual(U2, output["providerBaselines"]["uma"])
        source = output["sources"][0]
        self.assertEqual(U2, source["currentVersion"]["uma"])
        self.assertEqual(U, source["lastKnownGood"]["uma"])
        self.assertEqual(K, source["lastKnownGood"]["keiyoushi"])
        self.assertEqual("CANDIDATE", source["updateState"])
        self.assertFalse(source["publishEligible"])
        self.assertFalse(output["candidateContext"]["activeLastKnownGoodMutated"])

    def test_integration_failure_is_rejected(self):
        bad = handoff()
        bad["validationResults"]["integration"] = "failure"
        with self.assertRaisesRegex(M.CandidateRegistryError, "integration"):
            M.build_candidate_registry(base_registry(), bad)

    def test_changed_provider_validation_failure_is_rejected(self):
        bad = handoff()
        bad["validationResults"]["uma"] = "failure"
        with self.assertRaisesRegex(M.CandidateRegistryError, "validation did not succeed"):
            M.build_candidate_registry(base_registry(), bad)

    def test_source_lkg_mismatch_is_rejected(self):
        base = base_registry()
        base["sources"][0]["lastKnownGood"]["uma"] = "5" * 40
        with self.assertRaisesRegex(M.CandidateRegistryError, "LKG does not match"):
            M.build_candidate_registry(base, handoff())

    def test_handoff_that_allows_registry_mutation_is_rejected(self):
        with self.assertRaisesRegex(M.CandidateRegistryError, "forbid active registry mutation"):
            M.build_candidate_registry(base_registry(), handoff(registryMutationAllowed=True))

    def test_no_changed_provider_is_rejected(self):
        no_change = handoff()
        no_change["plan"]["providers"]["uma"] = {"lastKnownGood": U, "candidate": U, "changed": False}
        no_change["validationResults"]["uma"] = "skipped"
        with self.assertRaisesRegex(M.CandidateRegistryError, "no changed providers"):
            M.build_candidate_registry(base_registry(), no_change)


if __name__ == "__main__":
    unittest.main()
