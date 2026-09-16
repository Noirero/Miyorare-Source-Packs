import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("candidate_lifecycle", ROOT / "tools" / "candidate_lifecycle.py")
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

A = "a" * 40
B = "b" * 40
CANDIDATE_SET = "c" * 64


def status():
    return {
        "schema": 3,
        "providers": {
            "uma": {
                "updateState": "PROMOTED",
                "runtimeHealth": "HEALTHY",
                "activeCommit": A,
                "lastKnownGood": A,
                "healthyHistory": [A],
                "recoveryState": "IDLE",
                "reason": "per-source-runtime-probe",
            }
        },
    }


def pending():
    value = {
        "schemaVersion": 1,
        "maintenanceMode": "APPROVE_ONLY",
        "state": "WAITING_FOR_APPROVAL",
        "candidateSetId": CANDIDATE_SET,
        "gateFingerprint": "d" * 64,
        "providers": {
            "uma": {
                "current": A,
                "candidate": B,
                "state": "WAITING_FOR_APPROVAL",
            }
        },
        "ownerActionRequired": False,
        "publishEligible": False,
    }
    # Recompute a valid candidateSetId using the production helper contract.
    approval_spec = importlib.util.spec_from_file_location("approval_state_for_lifecycle", ROOT / "tools" / "approval_state.py")
    assert approval_spec and approval_spec.loader
    approval = importlib.util.module_from_spec(approval_spec)
    approval_spec.loader.exec_module(approval)
    identity = {
        "providers": {"uma": {"current": A, "candidate": B}},
        "gateFingerprint": value["gateFingerprint"],
    }
    value["candidateSetId"] = approval._digest(identity)
    return value


class CandidateLifecycleTests(unittest.TestCase):
    def test_stage_waiting_preserves_active_runtime_and_lkg(self):
        original = status()
        updated = M.stage_waiting(original, pending())
        provider = updated["providers"]["uma"]
        self.assertEqual("CANDIDATE", provider["updateState"])
        self.assertEqual(A, provider["activeCommit"])
        self.assertEqual(A, provider["lastKnownGood"])
        self.assertEqual("HEALTHY", provider["runtimeHealth"])
        self.assertEqual([A], provider["healthyHistory"])
        self.assertEqual("WAITING_FOR_APPROVAL", provider["candidate"]["approvalState"])
        self.assertFalse(provider["candidate"]["publishEligible"])

    def test_stage_rejects_stale_lkg(self):
        stale = status()
        stale["providers"]["uma"]["lastKnownGood"] = "e" * 40
        with self.assertRaisesRegex(M.CandidateLifecycleError, "stale"):
            M.stage_waiting(stale, pending())

    def test_stage_rejects_active_commit_mismatch(self):
        broken = status()
        broken["providers"]["uma"]["activeCommit"] = "e" * 40
        with self.assertRaisesRegex(M.CandidateLifecycleError, "activeCommit"):
            M.stage_waiting(broken, pending())

    def test_hold_candidate_preserves_runtime_health_and_lkg(self):
        updated = M.hold_candidate(status(), "uma", B, "compatibility-failure")
        provider = updated["providers"]["uma"]
        self.assertEqual("HELD", provider["updateState"])
        self.assertEqual(A, provider["activeCommit"])
        self.assertEqual(A, provider["lastKnownGood"])
        self.assertEqual("HEALTHY", provider["runtimeHealth"])
        self.assertFalse(provider["candidate"]["publishEligible"])


if __name__ == "__main__":
    unittest.main()
