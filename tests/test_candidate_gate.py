import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

SPEC = importlib.util.spec_from_file_location("candidate_gate", TOOLS / "candidate_gate.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
CONTRACT = json.loads((ROOT / "compatibility" / "contract.json").read_text(encoding="utf-8"))


def aggregate(*, candidate_pass: bool, release_gate: str, full: bool, suite_status: str = "PASS"):
    return {
        "schemaVersion": 1,
        "executionMode": "real-kotlin-parser-aggregate",
        "parserExecution": True,
        "suiteStatus": suite_status,
        "candidatePass": candidate_pass,
        "releaseGate": release_gate,
        "publishEligible": False,
        "ownerActionRequired": False,
        "coverage": {
            "canonicalExecuted": 12 if full else 8,
            "totalRegisteredSources": 12,
            "fullyExercisedSources": 12 if full else 4,
            "providerMembershipsExecuted": 21 if full else 12,
            "totalProviderMemberships": 21,
            "missingProviderMemberships": 0 if full else 9,
            "failingProviderMemberships": 0 if suite_status == "PASS" else 1,
            "fullCanonicalCoverage": full,
            "fullProviderMembershipCoverage": full,
        },
        "repairEvidence": {
            "reportedMemberships": 2,
            "validatedByRealParserRetest": 2,
            "failedRealParserRetest": 0,
        },
    }


class CandidateGateTests(unittest.TestCase):
    def test_partial_real_parser_coverage_stays_safe_not_ready_candidate(self):
        decision = MODULE.derive_candidate_gate(
            CONTRACT,
            aggregate(
                candidate_pass=False,
                release_gate="NOT_READY_PARTIAL_PARSER_HARNESS",
                full=False,
            ),
        )
        self.assertEqual("CANDIDATE", decision["updateState"])
        self.assertEqual("NOT_READY", decision["approvalState"])
        self.assertEqual("EXPAND_COMPATIBILITY_COVERAGE", decision["nextAction"])
        self.assertFalse(decision["ownerActionRequired"])
        self.assertFalse(decision["publishEligible"])

    def test_full_real_parser_pass_becomes_waiting_for_approval(self):
        decision = MODULE.derive_candidate_gate(
            CONTRACT,
            aggregate(candidate_pass=True, release_gate="REAL_PARSER_READY", full=True),
            {"currentRuntimeHealth": "HEALTHY"},
        )
        self.assertEqual("CANDIDATE", decision["updateState"])
        self.assertEqual("WAITING_FOR_APPROVAL", decision["approvalState"])
        self.assertEqual("WAITING_FOR_APPROVAL", decision["releaseGate"])
        self.assertEqual("WAIT_FOR_APPROVAL", decision["nextAction"])
        self.assertFalse(decision["publishEligible"])

    def test_validated_auto_repair_evidence_can_reach_waiting_for_approval(self):
        evidence = aggregate(candidate_pass=True, release_gate="REAL_PARSER_READY", full=True)
        evidence["executionMode"] = "real-kotlin-parser-aggregate-with-repair-evidence"
        decision = MODULE.derive_candidate_gate(
            CONTRACT,
            evidence,
            {"currentRuntimeHealth": "HEALTHY"},
        )
        self.assertEqual("WAITING_FOR_APPROVAL", decision["approvalState"])
        self.assertEqual("WAITING_FOR_APPROVAL", decision["releaseGate"])
        self.assertEqual(2, decision["evidence"]["repairEvidence"]["validatedByRealParserRetest"])
        self.assertFalse(decision["publishEligible"])

    def test_failed_auto_repair_retest_is_rejected_by_approval_gate(self):
        evidence = aggregate(candidate_pass=False, release_gate="BLOCKED_REAL_PARSER_FAILURE", full=False)
        evidence["executionMode"] = "real-kotlin-parser-aggregate-with-repair-evidence"
        evidence["repairEvidence"] = {
            "reportedMemberships": 2,
            "validatedByRealParserRetest": 1,
            "failedRealParserRetest": 1,
        }
        with self.assertRaisesRegex(MODULE.CandidateGateError, "failed auto-repair retest"):
            MODULE.derive_candidate_gate(CONTRACT, evidence)

    def test_approval_remains_dry_run_while_candidate_mode_is_enabled(self):
        decision = MODULE.derive_candidate_gate(
            CONTRACT,
            aggregate(candidate_pass=True, release_gate="REAL_PARSER_READY", full=True),
            {"currentRuntimeHealth": "HEALTHY", "approvalState": "APPROVED"},
        )
        self.assertEqual("APPROVED", decision["approvalState"])
        self.assertEqual("APPROVED_DRY_RUN", decision["releaseGate"])
        self.assertFalse(decision["publishEligible"])

    def test_parser_failure_starts_auto_repair_without_owner_assignment(self):
        decision = MODULE.derive_candidate_gate(
            CONTRACT,
            aggregate(
                candidate_pass=False,
                release_gate="BLOCKED_REAL_PARSER_FAILURE",
                full=False,
                suite_status="FAIL",
            ),
            {
                "currentRuntimeHealth": "HEALTHY",
                "selfRepairExhausted": False,
                "safeFallbackAvailable": True,
            },
        )
        self.assertEqual("HELD", decision["updateState"])
        self.assertEqual("AUTO_REPAIR_OR_DIAGNOSE", decision["nextAction"])
        self.assertFalse(decision["ownerActionRequired"])

    def test_exhausted_failed_candidate_keeps_healthy_current(self):
        decision = MODULE.derive_candidate_gate(
            CONTRACT,
            aggregate(
                candidate_pass=False,
                release_gate="BLOCKED_REAL_PARSER_FAILURE",
                full=False,
                suite_status="FAIL",
            ),
            {
                "currentRuntimeHealth": "HEALTHY",
                "selfRepairExhausted": True,
                "safeFallbackAvailable": True,
            },
        )
        self.assertEqual("AUTO_HOLD", decision["releaseGate"])
        self.assertEqual("KEEP_CURRENT", decision["nextAction"])
        self.assertFalse(decision["ownerActionRequired"])

    def test_regression_overrides_partial_coverage_and_blocks(self):
        decision = MODULE.derive_candidate_gate(
            CONTRACT,
            aggregate(
                candidate_pass=False,
                release_gate="NOT_READY_PARTIAL_PARSER_HARNESS",
                full=False,
            ),
            {"currentRuntimeHealth": "HEALTHY", "regressionDetected": True},
        )
        self.assertEqual("BLOCKED_REGRESSION", decision["releaseGate"])
        self.assertEqual("MIYORARE_REGRESSION", decision["failureClass"])
        self.assertFalse(decision["publishEligible"])

    def test_inconsistent_passing_aggregate_fails_closed(self):
        broken = aggregate(candidate_pass=True, release_gate="REAL_PARSER_READY", full=True)
        broken["coverage"]["fullProviderMembershipCoverage"] = False
        with self.assertRaisesRegex(MODULE.CandidateGateError, "requires full real-parser coverage"):
            MODULE.derive_candidate_gate(CONTRACT, broken)

    def test_aggregate_can_never_arrive_publish_eligible(self):
        broken = aggregate(candidate_pass=True, release_gate="REAL_PARSER_READY", full=True)
        broken["publishEligible"] = True
        with self.assertRaisesRegex(MODULE.CandidateGateError, "must never be publish eligible"):
            MODULE.derive_candidate_gate(CONTRACT, broken)


if __name__ == "__main__":
    unittest.main()
