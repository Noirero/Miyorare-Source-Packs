#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("d2", ROOT / "tools" / "source_lab_d2_provider_preference_recovery.py")
assert SPEC and SPEC.loader
D2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D2)

A = "a" * 40
B = "b" * 40
LUMOS = D2.LUMOS
SCOPED = "miyorare:inventory-id:SCOPED"
LEGACY = "miyorare:inventory-en:LEGACY"
READY_ID = "miyorare:inventory-id:READY"


def baseline() -> dict:
    return {
        "schemaVersion": 1,
        "phase": D2.PHASE,
        "readOnly": True,
        "sourcePacksAfterD1": A,
        "compatibilityFarmBaseline": B,
        "d1Artifact": {
            "runId": 1,
            "artifactId": 2,
            "name": "d1",
            "digest": "sha256:" + "1" * 64,
            "headSha": A,
            "requiredStatus": "D1_CONVERGENCE_BASELINE_CLEAN",
        },
        "requiredBehaviorProofs": [
            "sourcePendingWorker",
            "multiProviderPartialOnboarding",
            "a7LkgSafetyRegression",
            "farmApprovalState",
            "farmAuthorizedPromotion",
        ],
        "authorityFiles": {
            "workerTool": "tools/source_pending_worker.py",
            "approvalTool": "tools/source_pending_approval.py",
            "promotionWorkflow": ".github/workflows/source-lab-promote-candidate.yml",
            "farmApprovalTool": "tools/approval_state.py",
            "farmPromotionTool": "tools/authorized_promotion.py",
        },
        "requiredLumosAuthority": {
            "canonicalId": LUMOS,
            "providers": ["uma"],
            "selectedProviders": ["uma"],
            "workerState": "APPROVED",
        },
        "nextStage": D2.NEXT_STAGE,
    }


def d1() -> dict:
    return {
        "schemaVersion": 1,
        "phase": "TRACK_D_D1_CONVERGENCE_BASELINE",
        "readOnly": True,
        "status": "D1_CONVERGENCE_BASELINE_CLEAN",
        "trackDClosed": False,
        "nextStage": D2.PHASE,
        "d2Questions": [
            "prove source-scoped provider preference cannot regress to a failed provider",
            "prove candidate/LKG recovery remains isolated per provider/source",
            "prove stale READY evidence is invalidated after provider-baseline drift",
        ],
        "permanentAuthority": {"lkgSafety": "SAFE"},
        "safety": {"mutate": False},
    }


def a7() -> dict:
    return {
        "schemaVersion": 1,
        "phase": "A7_LKG_SAFETY",
        "status": "SAFE",
        "violations": [],
        "mutatesFoundation": False,
        "promotionAttempted": False,
    }


def registry() -> dict:
    return {
        "schemaVersion": 1,
        "providerBaselines": {"uma": A, "gekkoushi": B},
        "sources": [
            {
                "canonicalId": LUMOS,
                "providers": ["uma"],
                "currentVersion": {"uma": A},
                "lastKnownGood": {"uma": A},
                "compatibilityEnrollment": {"state": "ACTIVE"},
            },
            {
                "canonicalId": SCOPED,
                "providers": ["uma"],
                "upstreamIdentities": {"uma": {"file": "uma.kt"}},
                "currentVersion": {"uma": A},
                "lastKnownGood": {"uma": A},
                "compatibilityEnrollment": {"state": "ACTIVE"},
                "onboardingApproval": {
                    "state": "APPROVED",
                    "activeProviders": ["uma"],
                    "heldProviders": [{"provider": "gekkoushi", "state": "HELD", "reason": "failed"}],
                },
            },
            {
                "canonicalId": LEGACY,
                "providers": ["gekkoushi"],
                "currentVersion": {"gekkoushi": B},
                "lastKnownGood": {"gekkoushi": B},
                "compatibilityEnrollment": {"state": "ACTIVE"},
                "onboardingApproval": {"state": "APPROVED", "approvedAt": "2026-01-01T00:00:00Z"},
            },
            {
                "canonicalId": READY_ID,
                "providers": ["uma"],
                "currentVersion": {"uma": A},
                "lastKnownGood": {"uma": A},
                "compatibilityEnrollment": {"state": "PENDING"},
            },
        ],
    }


def worker() -> dict:
    return {
        "schemaVersion": 2,
        "sources": {
            LUMOS: {"state": "APPROVED", "selectedProviders": ["uma"]},
            READY_ID: {
                "state": D2.READY,
                "approvalState": "WAITING_FOR_APPROVAL",
                "publishEligible": False,
                "selectedProviders": ["uma"],
                "testedVersions": {"uma": A},
            },
        },
    }


def manifest() -> dict:
    return {"schemaVersion": 1, "proofs": {name: {"passed": True} for name in baseline()["requiredBehaviorProofs"]}}


def authority_code() -> dict[str, str]:
    return {
        "workerTool": "\n".join([
            "def ready_evidence_is_stale(", "def invalidate_stale_ready(", 'entry["state"] = RETRY',
            'entry["approvalState"] = "NOT_READY"', 'entry["revalidationReason"] = "PROVIDER_BASELINE_CHANGED"',
            "baseline_reset = is_retry and retry_evidence_is_stale",
        ]),
        "approvalTool": "\n".join([
            'source["providers"] = list(active_providers)', 'source["upstreamIdentities"] = {',
            'source["onboardingApproval"] = {', '"activeProviders": list(active_providers)',
            '"heldProviders": item["heldProviders"]', 'raise ValueError("approval plan changed; refusing stale approval")',
        ]),
        "promotionWorkflow": "\n".join([
            "approval sourceScope changed", "scoped source is not a {provider} member", "source state moved",
            "active/LKG moved", 'entry["state"] = "RETRY"', 'entry["revalidationReason"] = "PROVIDER_BASELINE_CHANGED"',
            'entry["invalidatedByPromotionRunId"]', "Refuse promotion if foundation moved after validation",
        ]),
        "farmApprovalTool": "\n".join([
            "def validate_source_scope(", "approval sourceScope does not match pending candidate",
            "registry changed after staging; approval is stale",
        ]),
        "farmPromotionTool": "\n".join([
            "authorization sourceScope does not match requested/pending sourceScope",
            "registry lastKnownGood changed after authorization; approval is stale", "Source-level LKG mutation is",
        ]),
    }


class D2Tests(unittest.TestCase):
    def build(self, reg=None, work=None, proofs=None, code=None, a7_report=None):
        return D2.build_report(
            baseline(), d1(), a7_report or a7(), reg or registry(), work or worker(), proofs or manifest(),
            code or authority_code(), {"controlHead": A, "compatibilityFarm": B},
        )

    def test_clean_acceptance_proves_all_three_d2_invariants(self):
        report = self.build()
        preference = report["proofs"]["providerPreference"]
        self.assertEqual(report["status"], "D2_PROVIDER_PREFERENCE_RECOVERY_PROVEN")
        self.assertFalse(report["trackDClosed"])
        self.assertEqual(report["nextStage"], D2.NEXT_STAGE)
        self.assertEqual(preference["status"], "PROVEN")
        self.assertEqual(preference["scopedApprovedSourceCount"], 1)
        self.assertEqual(preference["legacyProviderWideApprovals"], [LEGACY])
        self.assertEqual(report["proofs"]["candidateLkgRecoveryIsolation"]["status"], "PROVEN")
        self.assertEqual(report["proofs"]["staleReadyInvalidation"]["liveReadyCount"], 1)
        self.assertFalse(any(report["safety"].values()))

    def test_historical_provider_wide_approval_is_not_misread_as_partial_scope(self):
        report = self.build()
        preference = report["proofs"]["providerPreference"]
        self.assertEqual(preference["legacyProviderWideApprovalCount"], 1)
        self.assertNotIn(LEGACY, [row["canonicalId"] for row in preference["scopedApprovedSources"]])

    def test_one_sided_partial_provider_authority_fails_closed(self):
        reg = registry()
        legacy = next(row for row in reg["sources"] if row["canonicalId"] == LEGACY)
        legacy["onboardingApproval"]["activeProviders"] = ["gekkoushi"]
        with self.assertRaisesRegex(D2.D2Error, "onboarding provider authority malformed"):
            self.build(reg=reg)

    def test_held_provider_cannot_reenter_scoped_active_authority(self):
        reg = registry()
        scoped = next(row for row in reg["sources"] if row["canonicalId"] == SCOPED)
        scoped["providers"] = ["uma", "gekkoushi"]
        with self.assertRaisesRegex(D2.D2Error, "active provider set|held provider"):
            self.build(reg=reg)

    def test_stale_ready_is_rejected_from_live_authority(self):
        work = worker()
        work["sources"][READY_ID]["testedVersions"]["uma"] = B
        with self.assertRaisesRegex(D2.D2Error, "stale READY"):
            self.build(work=work)

    def test_failed_behavior_proof_fails_closed(self):
        proofs = manifest()
        proofs["proofs"]["farmAuthorizedPromotion"]["passed"] = False
        with self.assertRaisesRegex(D2.D2Error, "behavior proof failed"):
            self.build(proofs=proofs)

    def test_missing_authority_marker_fails_closed(self):
        code = authority_code()
        code["promotionWorkflow"] = code["promotionWorkflow"].replace("active/LKG moved", "")
        with self.assertRaisesRegex(D2.D2Error, "invariant markers missing"):
            self.build(code=code)

    def test_unsafe_a7_fails_closed(self):
        broken = deepcopy(a7())
        broken["status"] = "UNSAFE"
        broken["violations"] = ["candidate leaked"]
        with self.assertRaisesRegex(D2.D2Error, "A7 LKG safety"):
            self.build(a7_report=broken)

    def test_farm_ref_drift_fails_closed(self):
        with self.assertRaisesRegex(D2.D2Error, "Farm moved"):
            D2.build_report(
                baseline(), d1(), a7(), registry(), worker(), manifest(), authority_code(),
                {"controlHead": A, "compatibilityFarm": "c" * 40},
            )


if __name__ == "__main__":
    unittest.main()
