import importlib.util
import unittest
from copy import deepcopy
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


def scoped_pending(sources=None):
    scoped_gate = gate()
    scoped_gate["sourceScope"] = {"uma": sources if sources is not None else ["SOURCE_A", "SOURCE_B"]}
    return M.build_pending(registry(), plan(), scoped_gate, evidence())


class SourceScopeApprovalTests(unittest.TestCase):
    def test_scope_flows_through_identity_approval_and_authorization(self):
        pending = scoped_pending(["SOURCE_B", "SOURCE_A"])
        scope = {"uma": ["SOURCE_A", "SOURCE_B"]}
        self.assertEqual(scope, pending["sourceScope"])
        identity = {
            "providers": {"uma": {"current": A, "candidate": B}},
            "gateFingerprint": pending["gateFingerprint"],
            "evidenceBinding": evidence(),
        }
        self.assertNotEqual(M._digest(identity), pending["candidateSetId"])
        identity["sourceScope"] = scope
        self.assertEqual(M._digest(identity), pending["candidateSetId"])
        approval = M.approve_pending(pending, pending["candidateSetId"], "Noirero")
        auth = M.authorize_promotion(registry(), pending, approval, "uma", B, scope)
        self.assertEqual(scope, approval["sourceScope"])
        self.assertEqual(scope, auth["sourceScope"])
        self.assertEqual(pending["candidateSetId"], auth["candidateSetId"])
        self.assertFalse(auth["publishEligible"])
        approval["sourceScope"]["uma"].append("SOURCE_C")
        self.assertEqual(scope, pending["sourceScope"])
        self.assertEqual(scope, auth["sourceScope"])

    def test_legacy_identity_is_unchanged_and_cannot_be_used_as_partial(self):
        pending = M.build_pending(registry(), plan(), gate(), evidence())
        self.assertEqual(M._digest({
            "providers": {"uma": {"current": A, "candidate": B}},
            "gateFingerprint": M._digest(gate()), "evidenceBinding": evidence(),
        }), pending["candidateSetId"])
        approval = M.approve_pending(pending, pending["candidateSetId"], "Noirero")
        self.assertNotIn("sourceScope", approval)
        with self.assertRaisesRegex(M.ApprovalStateError, "legacy provider-wide"):
            M.authorize_promotion(registry(), pending, approval, "uma", B, {"uma": ["SOURCE_A"]})

    def test_scope_mutations_after_staging_reject(self):
        for scope in ({"uma": ["SOURCE_A", "SOURCE_B", "SOURCE_C"]},
                      {"uma": ["SOURCE_A"]}, {"uma": ["SOURCE_A", "SOURCE_C"]},
                      {"keiyoushi": ["SOURCE_A", "SOURCE_B"]}, None):
            with self.subTest(scope=scope):
                pending = scoped_pending()
                if scope is None:
                    del pending["sourceScope"]
                else:
                    pending["sourceScope"] = scope
                with self.assertRaises(M.ApprovalStateError):
                    M.approve_pending(pending, pending["candidateSetId"], "Noirero")

    def test_malformed_scope_cannot_be_staged(self):
        for scope in (None, {}, [], {"uma": []}, {"uma": ["A", "A"]},
                      {"uma": [""]}, {"uma": [" A"]}, {"uma": [42]},
                      {"keiyoushi": ["A"]}, {"uma": ["A"], "keiyoushi": ["B"]}):
            with self.subTest(scope=scope):
                bad = gate()
                bad["sourceScope"] = scope
                with self.assertRaises(M.ApprovalStateError):
                    M.build_pending(registry(), plan(), bad, evidence())

    def test_approval_and_requested_scope_must_both_match(self):
        pending = scoped_pending()
        approval = M.approve_pending(pending, pending["candidateSetId"], "Noirero")
        for scope in ({"uma": ["SOURCE_A", "SOURCE_B", "SOURCE_C"]},
                      {"uma": ["SOURCE_A"]}, {"uma": ["SOURCE_A", "SOURCE_C"]},
                      {"keiyoushi": ["SOURCE_A", "SOURCE_B"]}, None):
            with self.subTest(scope=scope):
                with self.assertRaises(M.ApprovalStateError):
                    M.authorize_promotion(registry(), pending, approval, "uma", B, scope)
                changed = deepcopy(approval)
                if scope is None:
                    del changed["sourceScope"]
                else:
                    changed["sourceScope"] = scope
                with self.assertRaisesRegex(M.ApprovalStateError, "approval sourceScope"):
                    M.authorize_promotion(registry(), pending, changed, "uma", B, pending["sourceScope"])

    def test_other_candidate_or_scope_approval_cannot_be_replayed(self):
        pending = scoped_pending()
        other_scope = scoped_pending(["SOURCE_C"])
        other_plan = plan()
        other_plan["providers"]["uma"]["candidate"] = D
        other_gate = gate()
        other_gate["sourceScope"] = pending["sourceScope"]
        other_candidate = M.build_pending(registry(), other_plan, other_gate, evidence())
        for other in (other_scope, other_candidate):
            with self.subTest(other=other["candidateSetId"]):
                self.assertNotEqual(pending["candidateSetId"], other["candidateSetId"])
                approval = M.approve_pending(other, other["candidateSetId"], "Noirero")
                with self.assertRaisesRegex(M.ApprovalStateError, "different candidate set"):
                    M.authorize_promotion(registry(), pending, approval, "uma", B, pending["sourceScope"])

    def test_provider_relationship_is_bound_even_with_multiple_candidates(self):
        multi_plan = plan()
        multi_plan["providers"]["keiyoushi"].update(changed=True, candidate=D)
        multi_gate = gate()
        multi_gate["sourceScope"] = {"uma": ["SOURCE_A"], "keiyoushi": ["SOURCE_B"]}
        pending = M.build_pending(registry(), multi_plan, multi_gate, evidence())
        pending["sourceScope"] = {"uma": ["SOURCE_B"], "keiyoushi": ["SOURCE_A"]}
        with self.assertRaisesRegex(M.ApprovalStateError, "candidateSetId"):
            M.validate_pending(pending)

    def test_scoped_stale_registry_candidate_and_evidence_guards_remain(self):
        pending = scoped_pending()
        approval = M.approve_pending(pending, pending["candidateSetId"], "Noirero")
        stale = registry()
        stale["providers"]["uma"]["lastKnownGood"] = D
        with self.assertRaisesRegex(M.ApprovalStateError, "stale"):
            M.authorize_promotion(stale, pending, approval, "uma", B, pending["sourceScope"])
        with self.assertRaisesRegex(M.ApprovalStateError, "SHA"):
            M.authorize_promotion(registry(), pending, approval, "uma", D, pending["sourceScope"])
        approval["evidenceBinding"]["farmEvidenceSha256"] = "4" * 64
        with self.assertRaisesRegex(M.ApprovalStateError, "evidence binding"):
            M.authorize_promotion(registry(), pending, approval, "uma", B, pending["sourceScope"])

    def test_scope_does_not_relax_gate(self):
        bad = gate()
        bad["sourceScope"] = {"uma": ["SOURCE_A"]}
        bad["evidence"]["candidatePass"] = False
        with self.assertRaisesRegex(M.ApprovalStateError, "passing Compatibility Farm"):
            M.build_pending(registry(), plan(), bad, evidence())


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
