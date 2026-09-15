import importlib.util
import json
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "compatibility_contract",
    ROOT / "tools" / "compatibility_contract.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
CONTRACT = json.loads((ROOT / "compatibility" / "contract.json").read_text(encoding="utf-8"))


class CompatibilityContractTests(unittest.TestCase):
    def test_contract_is_valid(self):
        MODULE.validate_contract(CONTRACT)

    def test_unknown_candidate_failure_starts_auto_diagnose_not_manual_work(self):
        decision = MODULE.evaluate_candidate(
            CONTRACT,
            {
                "candidatePass": False,
                "currentRuntimeHealth": "HEALTHY",
                "failureClass": "UNKNOWN",
                "regressionDetected": False,
                "safeFallbackAvailable": True,
                "selfRepairExhausted": False,
            },
        )
        self.assertEqual("HELD", decision["updateState"])
        self.assertEqual("AUTO_DIAGNOSE", decision["nextAction"])
        self.assertFalse(decision["ownerActionRequired"])
        self.assertFalse(decision["publishEligible"])

    def test_failed_candidate_keeps_healthy_current_without_owner_assignment(self):
        decision = MODULE.evaluate_candidate(
            CONTRACT,
            {
                "candidatePass": False,
                "currentRuntimeHealth": "HEALTHY",
                "failureClass": "PARSER_FAILURE",
                "regressionDetected": False,
                "safeFallbackAvailable": True,
                "selfRepairExhausted": True,
            },
        )
        self.assertEqual("AUTO_HOLD", decision["releaseGate"])
        self.assertEqual("KEEP_CURRENT", decision["nextAction"])
        self.assertFalse(decision["ownerActionRequired"])

    def test_regression_budget_is_zero_and_blocks_release(self):
        decision = MODULE.evaluate_candidate(
            CONTRACT,
            {
                "candidatePass": True,
                "currentRuntimeHealth": "HEALTHY",
                "regressionDetected": True,
                "safeFallbackAvailable": True,
                "selfRepairExhausted": False,
            },
        )
        self.assertEqual("BLOCKED_REGRESSION", decision["releaseGate"])
        self.assertEqual("MIYORARE_REGRESSION", decision["failureClass"])
        self.assertFalse(decision["publishEligible"])

    def test_passing_candidate_waits_for_approval(self):
        decision = MODULE.evaluate_candidate(
            CONTRACT,
            {
                "candidatePass": True,
                "currentRuntimeHealth": "HEALTHY",
                "regressionDetected": False,
            },
        )
        self.assertEqual("CANDIDATE", decision["updateState"])
        self.assertEqual("WAITING_FOR_APPROVAL", decision["approvalState"])
        self.assertEqual("WAITING_FOR_APPROVAL", decision["releaseGate"])
        self.assertFalse(decision["publishEligible"])

    def test_candidate_mode_stays_dry_run_even_after_approval(self):
        decision = MODULE.evaluate_candidate(
            CONTRACT,
            {
                "candidatePass": True,
                "currentRuntimeHealth": "HEALTHY",
                "regressionDetected": False,
                "approvalState": "APPROVED",
            },
        )
        self.assertEqual("APPROVED_DRY_RUN", decision["releaseGate"])
        self.assertFalse(decision["publishEligible"])

    def test_engineering_escalation_is_exceptional_last_resort(self):
        decision = MODULE.evaluate_candidate(
            CONTRACT,
            {
                "candidatePass": False,
                "currentRuntimeHealth": "BROKEN",
                "failureClass": "UNKNOWN",
                "regressionDetected": False,
                "safeFallbackAvailable": False,
                "selfRepairExhausted": True,
            },
        )
        self.assertEqual("TEMPORARILY_UNAVAILABLE", decision["releaseGate"])
        self.assertEqual("ENGINEERING_ESCALATION_REQUIRED", decision["nextAction"])
        self.assertTrue(decision["ownerActionRequired"])

    def test_missing_required_failure_class_is_rejected(self):
        invalid = deepcopy(CONTRACT)
        invalid["failureClasses"].remove("UNKNOWN")
        with self.assertRaises(MODULE.ContractError):
            MODULE.validate_contract(invalid)


if __name__ == "__main__":
    unittest.main()
