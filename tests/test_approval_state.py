import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("approval_state", ROOT / "tools" / "approval_state.py")
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

A = "a" * 40
B = "b" * 40
C = "c" * 40
D = "d" * 40


def registry():
    return {"providers": {"uma": {"lastKnownGood": A}, "keiyoushi": {"lastKnownGood": C}}}


def plan():
    return {
        "schema": 1,
        "providers": {
            "uma": {"lastKnownGood": A, "candidate": B, "changed": True},
            "keiyoushi": {"lastKnownGood": C, "candidate": C, "changed": False},
        },
    }


def gate():
    return {
        "maintenanceMode": "APPROVE_ONLY",
        "candidateMode": True,
        "updateState": "CANDIDATE",
        "approvalState": "WAITING_FOR_APPROVAL",
        "releaseGate": "WAITING_FOR_APPROVAL",
        "nextAction": "WAIT_FOR_APPROVAL",
        "ownerActionRequired": False,
        "publishEligible": False,
        "evidence": {
            "candidatePass": True,
            "coverage": {"fullCanonicalCoverage": True, "fullProviderMembershipCoverage": True},
        },
    }


def evidence():
    return {
        "schemaVersion": 1,
        "farmEvidenceSha256": "1" * 64,
        "gateSha256": "2" * 64,
        "repairEvidenceSha256": "3" * 64,
        "repairEvidenceCount": 2,
    }


class ApprovalStateTests(unittest.TestCase):
    def test_stage_approve_authorize_happy_path(self):
        pending = M.build_pending(registry(), plan(), gate(), evidence())
        self.assertEqual("WAITING_FOR_APPROVAL", pending["state"])
        self.assertFalse(pending["publishEligible"])
        self.assertEqual({"uma"}, set(pending["providers"]))
        self.assertEqual(evidence(), pending["evidenceBinding"])
        approval = M.approve_pending(pending, pending["candidateSetId"], "Noirero")
        auth = M.authorize_promotion(registry(), pending, approval, "uma", B)
        self.assertTrue(auth["authorized"])
        self.assertEqual(B, auth["commit"])
        self.assertEqual(evidence(), auth["evidenceBinding"])
        self.assertFalse(auth["publishEligible"])

    def test_approval_for_different_candidate_set_is_rejected(self):
        pending = M.build_pending(registry(), plan(), gate(), evidence())
        with self.assertRaisesRegex(M.ApprovalStateError, "does not match"):
            M.approve_pending(pending, "0" * 64, "Noirero")

    def test_candidate_content_tampering_invalidates_pending_id(self):
        pending = M.build_pending(registry(), plan(), gate(), evidence())
        pending["providers"]["uma"]["candidate"] = D
        with self.assertRaisesRegex(M.ApprovalStateError, "candidateSetId does not match"):
            M.validate_pending(pending)

    def test_farm_evidence_change_invalidates_pending_id(self):
        pending = M.build_pending(registry(), plan(), gate(), evidence())
        pending["evidenceBinding"]["farmEvidenceSha256"] = "4" * 64
        with self.assertRaisesRegex(M.ApprovalStateError, "candidateSetId does not match"):
            M.validate_pending(pending)

    def test_repair_evidence_change_invalidates_pending_id(self):
        pending = M.build_pending(registry(), plan(), gate(), evidence())
        pending["evidenceBinding"]["repairEvidenceSha256"] = "4" * 64
        with self.assertRaisesRegex(M.ApprovalStateError, "candidateSetId does not match"):
            M.validate_pending(pending)

    def test_approval_evidence_mismatch_is_rejected(self):
        pending = M.build_pending(registry(), plan(), gate(), evidence())
        approval = M.approve_pending(pending, pending["candidateSetId"], "Noirero")
        approval["evidenceBinding"]["repairEvidenceSha256"] = "4" * 64
        with self.assertRaisesRegex(M.ApprovalStateError, "evidence binding"):
            M.authorize_promotion(registry(), pending, approval, "uma", B)

    def test_registry_change_after_approval_makes_authorization_stale(self):
        pending = M.build_pending(registry(), plan(), gate(), evidence())
        approval = M.approve_pending(pending, pending["candidateSetId"], "Noirero")
        changed = registry()
        changed["providers"]["uma"]["lastKnownGood"] = D
        with self.assertRaisesRegex(M.ApprovalStateError, "approval is stale"):
            M.authorize_promotion(changed, pending, approval, "uma", B)

    def test_different_promotion_sha_is_rejected(self):
        pending = M.build_pending(registry(), plan(), gate(), evidence())
        approval = M.approve_pending(pending, pending["candidateSetId"], "Noirero")
        with self.assertRaisesRegex(M.ApprovalStateError, "does not match approved candidate"):
            M.authorize_promotion(registry(), pending, approval, "uma", D)

    def test_incomplete_gate_cannot_be_staged(self):
        bad = gate()
        bad["evidence"]["coverage"]["fullProviderMembershipCoverage"] = False
        with self.assertRaisesRegex(M.ApprovalStateError, "full provider membership"):
            M.build_pending(registry(), plan(), bad, evidence())

    def test_plan_stale_against_registry_is_rejected(self):
        stale = plan()
        stale["providers"]["uma"]["lastKnownGood"] = D
        with self.assertRaisesRegex(M.ApprovalStateError, "plan is stale"):
            M.build_pending(registry(), stale, gate(), evidence())

    def test_no_changed_candidate_cannot_be_staged(self):
        no_change = plan()
        no_change["providers"]["uma"]["changed"] = False
        with self.assertRaisesRegex(M.ApprovalStateError, "no changed"):
            M.build_pending(registry(), no_change, gate(), evidence())

    def test_candidate_set_id_changes_when_candidate_changes(self):
        one = M.build_pending(registry(), plan(), gate(), evidence())
        p2 = plan()
        p2["providers"]["uma"]["candidate"] = D
        two = M.build_pending(registry(), p2, gate(), evidence())
        self.assertNotEqual(one["candidateSetId"], two["candidateSetId"])

    def test_candidate_set_id_changes_when_evidence_changes(self):
        one = M.build_pending(registry(), plan(), gate(), evidence())
        changed = evidence()
        changed["repairEvidenceSha256"] = "5" * 64
        two = M.build_pending(registry(), plan(), gate(), changed)
        self.assertNotEqual(one["candidateSetId"], two["candidateSetId"])


if __name__ == "__main__":
    unittest.main()
