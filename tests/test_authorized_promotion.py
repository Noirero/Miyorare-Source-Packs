import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("authorized_promotion", ROOT / "tools" / "authorized_promotion.py")
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

A = "a" * 40
B = "b" * 40
CANDIDATE_SET = "c" * 64


def registry():
    return {"schema": 1, "providers": {"uma": {"upstreamBase": A, "lastKnownGood": A}}}


def authorization(**overrides):
    value = {
        "schemaVersion": 1, "authorized": True, "maintenanceMode": "APPROVE_ONLY",
        "candidateSetId": CANDIDATE_SET, "provider": "uma", "expectedCurrent": A,
        "commit": B, "approvedBy": "Noirero", "gateFingerprint": "d" * 64,
        "evidenceBinding": {
            "schemaVersion": 1, "farmEvidenceSha256": "1" * 64,
            "gateSha256": "2" * 64, "repairEvidenceSha256": "3" * 64,
            "repairEvidenceCount": 2,
        },
        "publishEligible": False,
    }
    value.update(overrides)
    return value


class AuthorizedPromotionTests(unittest.TestCase):
    def test_exact_authorization_promotes_without_publish_eligibility(self):
        auth = authorization()
        updated, receipt = M.apply_authorized_promotion(registry(), auth, "uma", B)
        self.assertEqual(B, updated["providers"]["uma"]["lastKnownGood"])
        self.assertEqual(B, updated["providers"]["uma"]["upstreamBase"])
        self.assertEqual(A, receipt["previousLastKnownGood"])
        self.assertEqual(auth["evidenceBinding"], receipt["evidenceBinding"])
        self.assertFalse(receipt["publishEligible"])

    def test_missing_authorization_is_rejected(self):
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "explicitly authorized"):
            M.apply_authorized_promotion(registry(), authorization(authorized=False), "uma", B)

    def test_provider_mismatch_is_rejected(self):
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "provider"):
            M.apply_authorized_promotion(registry(), authorization(provider="keiyoushi"), "uma", B)

    def test_candidate_sha_mismatch_is_rejected(self):
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "does not match authorization"):
            M.apply_authorized_promotion(registry(), authorization(), "uma", "d" * 40)

    def test_expected_lkg_change_is_rejected_as_stale(self):
        changed = registry()
        changed["providers"]["uma"]["lastKnownGood"] = "d" * 40
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "approval is stale"):
            M.apply_authorized_promotion(changed, authorization(), "uma", B)

    def test_publish_eligible_authorization_is_rejected(self):
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "must not be publish eligible"):
            M.apply_authorized_promotion(registry(), authorization(publishEligible=True), "uma", B)

    def test_candidate_set_id_must_be_digest(self):
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "candidateSetId"):
            M.apply_authorized_promotion(registry(), authorization(candidateSetId="bad"), "uma", B)

    def test_evidence_binding_is_required(self):
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "evidenceBinding"):
            M.apply_authorized_promotion(registry(), authorization(evidenceBinding=None), "uma", B)

    def test_tampered_evidence_digest_is_rejected(self):
        auth = authorization()
        tampered = deepcopy(auth["evidenceBinding"])
        tampered["repairEvidenceSha256"] = "bad"
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "repairEvidenceSha256"):
            M.apply_authorized_promotion(registry(), authorization(evidenceBinding=tampered), "uma", B)

    def test_authorization_replay_is_rejected(self):
        promoted = registry()
        promoted["providers"]["uma"]["lastKnownGood"] = B
        promoted["providers"]["uma"]["upstreamBase"] = B
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "replay rejected"):
            M.apply_authorized_promotion(promoted, authorization(expectedCurrent=B), "uma", B)


class ScopedAuthorizationTests(unittest.TestCase):
    def setUp(self):
        from tests.test_approval_state import M as approval, scoped_pending, registry as approval_registry
        self.pending = scoped_pending()
        self.scope = deepcopy(self.pending["sourceScope"])
        proof = approval.approve_pending(self.pending, self.pending["candidateSetId"], "Noirero")
        self.auth = approval.authorize_promotion(approval_registry(), self.pending, proof, "uma", B, self.scope)

    def test_exact_scoped_authorization_validates(self):
        M.validate_authorization(self.auth, "uma", B, self.scope, self.pending)

    def test_exact_scoped_authorization_advances_reference_and_preserves_scope(self):
        updated, receipt = M.apply_authorized_promotion(
            registry(), self.auth, "uma", B, self.scope, self.pending
        )
        self.assertEqual(B, updated["providers"]["uma"]["lastKnownGood"])
        self.assertEqual(B, updated["providers"]["uma"]["upstreamBase"])
        self.assertEqual(self.scope, receipt["sourceScope"])
        self.assertEqual(A, receipt["previousLastKnownGood"])
        self.assertFalse(receipt["publishEligible"])

    def test_scoped_promotion_requires_authoritative_identity_and_scope(self):
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "pending candidate identity"):
            M.validate_authorization(self.auth, "uma", B, self.scope)
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "sourceScope"):
            M.validate_authorization(self.auth, "uma", B, pending=self.pending)
        with self.assertRaises(M.AuthorizedPromotionError):
            M.apply_authorized_promotion(registry(), self.auth, "uma", B)

    def test_authorization_scope_add_remove_swap_and_strip_reject(self):
        for scope in ({"uma": ["SOURCE_A", "SOURCE_B", "SOURCE_C"]},
                      {"uma": ["SOURCE_A"]}, {"uma": ["SOURCE_A", "SOURCE_C"]},
                      {"keiyoushi": ["SOURCE_A", "SOURCE_B"]}, None):
            with self.subTest(scope=scope):
                changed = deepcopy(self.auth)
                if scope is None:
                    del changed["sourceScope"]
                else:
                    changed["sourceScope"] = scope
                with self.assertRaisesRegex(M.AuthorizedPromotionError, "sourceScope"):
                    M.validate_authorization(changed, "uma", B, self.scope, self.pending)
                with self.assertRaisesRegex(M.AuthorizedPromotionError, "sourceScope"):
                    M.validate_authorization(self.auth, "uma", B, scope, self.pending)

    def test_foreign_candidate_or_scope_authorization_rejects(self):
        from tests.test_approval_state import M as approval, scoped_pending, registry as approval_registry, plan, gate, evidence
        other_gate = gate()
        other_gate["sourceScope"] = self.scope
        other_plan = plan()
        other_plan["providers"]["uma"]["candidate"] = "d" * 40
        other_candidate = approval.build_pending(approval_registry(), other_plan, other_gate, evidence())
        for other in (scoped_pending(["SOURCE_C"]), other_candidate):
            proof = approval.approve_pending(other, other["candidateSetId"], "Noirero")
            commit = other["providers"]["uma"]["candidate"]
            auth = approval.authorize_promotion(approval_registry(), other, proof, "uma", commit, other["sourceScope"])
            with self.assertRaises(M.AuthorizedPromotionError):
                M.validate_authorization(auth, "uma", B, self.scope, self.pending)

    def test_authorization_identity_evidence_and_current_mismatch_reject(self):
        for key, value in (("candidateSetId", "9" * 64), ("gateFingerprint", "9" * 64),
                           ("expectedCurrent", "9" * 40), ("commit", "9" * 40),
                           ("provider", "keiyoushi"), ("publishEligible", True)):
            with self.subTest(key=key):
                changed = deepcopy(self.auth)
                changed[key] = value
                with self.assertRaises(M.AuthorizedPromotionError):
                    M.validate_authorization(changed, "uma", B, self.scope, self.pending)
        changed = deepcopy(self.auth)
        changed["evidenceBinding"]["gateSha256"] = "9" * 64
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "evidenceBinding"):
            M.validate_authorization(changed, "uma", B, self.scope, self.pending)

    def test_legacy_authorization_cannot_be_used_as_scoped(self):
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "sourceScope"):
            M.validate_authorization(authorization(), "uma", B, self.scope, self.pending)
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "legacy provider-wide"):
            M.apply_authorized_promotion(registry(), authorization(), "uma", B, self.scope, self.pending)


if __name__ == "__main__":
    unittest.main()
