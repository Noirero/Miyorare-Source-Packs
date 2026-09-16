import importlib.util
import unittest
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
    return {
        "schema": 1,
        "providers": {
            "uma": {
                "upstreamBase": A,
                "lastKnownGood": A,
            }
        },
    }


def authorization(**overrides):
    value = {
        "schemaVersion": 1,
        "authorized": True,
        "maintenanceMode": "APPROVE_ONLY",
        "candidateSetId": CANDIDATE_SET,
        "provider": "uma",
        "expectedCurrent": A,
        "commit": B,
        "approvedBy": "Noirero",
        "publishEligible": False,
    }
    value.update(overrides)
    return value


class AuthorizedPromotionTests(unittest.TestCase):
    def test_exact_authorization_promotes_without_publish_eligibility(self):
        updated, receipt = M.apply_authorized_promotion(registry(), authorization(), "uma", B)
        self.assertEqual(B, updated["providers"]["uma"]["lastKnownGood"])
        self.assertEqual(B, updated["providers"]["uma"]["upstreamBase"])
        self.assertEqual(A, receipt["previousLastKnownGood"])
        self.assertFalse(receipt["publishEligible"])

    def test_missing_authorization_is_rejected(self):
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "explicitly authorized"):
            M.apply_authorized_promotion(registry(), authorization(authorized=False), "uma", B)

    def test_provider_mismatch_is_rejected(self):
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "provider"):
            M.apply_authorized_promotion(registry(), authorization(provider="keiyoushi"), "uma", B)

    def test_candidate_sha_mismatch_is_rejected(self):
        other = "d" * 40
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "does not match authorization"):
            M.apply_authorized_promotion(registry(), authorization(), "uma", other)

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

    def test_authorization_replay_is_rejected(self):
        promoted = registry()
        promoted["providers"]["uma"]["lastKnownGood"] = B
        promoted["providers"]["uma"]["upstreamBase"] = B
        replay = authorization(expectedCurrent=B)
        with self.assertRaisesRegex(M.AuthorizedPromotionError, "replay rejected"):
            M.apply_authorized_promotion(promoted, replay, "uma", B)


if __name__ == "__main__":
    unittest.main()
