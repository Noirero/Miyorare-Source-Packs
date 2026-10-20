from __future__ import annotations

import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "d4", ROOT / "tools" / "source_lab_d4_long_term_automation_acceptance.py"
)
assert SPEC and SPEC.loader
D4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D4)

A = "a" * 40
B = "b" * 40
C = "c" * 40
D = "d" * 40
HANDOFF = "miyorare:inventory-id:SOFTKOMIK"


def baseline() -> dict:
    return {
        "schemaVersion": 1,
        "phase": D4.PHASE,
        "readOnlyAcceptance": True,
        "sourcePacksAfterD3": A,
        "compatibilityFarmBaseline": B,
        "miyorareAmain2Baseline": C,
        "d3Artifact": {
            "runId": 3,
            "artifactId": 4,
            "name": "d3",
            "digest": "sha256:" + "1" * 64,
            "headSha": D,
            "requiredStatus": "D3_UNIFIED_DRIFT_HEALTH_PROVEN_WITH_OWNER_PACK_HANDOFFS",
        },
        "permanentChain": {
            "upstreamDetection": "auto",
            "runtimeValidation": "worker",
            "sourceApproval": "source-approval",
            "providerPromotion": "promotion",
            "lkgSafety": "a7",
            "releaseController": "controller",
            "releasePublisher": "publisher",
            "releaseSeal": "seal",
            "promotionAuthority": "authority",
        },
        "requiredAcceptance": ["a", "b", "c", "d", "e"],
        "nextStage": D4.NEXT_STAGE,
    }


def d3() -> dict:
    return {
        "schemaVersion": 1,
        "phase": D4.D3_PHASE,
        "readOnlyAcceptance": True,
        "status": "D3_UNIFIED_DRIFT_HEALTH_PROVEN_WITH_OWNER_PACK_HANDOFFS",
        "trackDClosed": False,
        "nextStage": D4.PHASE,
        "operationalHandoffs": {
            "count": 1,
            "ownerPackAuthorityRequired": [HANDOFF],
        },
        "safety": {"mutate": False},
    }


def d2() -> dict:
    return {
        "schemaVersion": 1,
        "phase": D4.D2_PHASE,
        "readOnly": True,
        "status": D4.D2_STATUS,
        "trackDClosed": False,
        "nextStage": D4.D3_PHASE,
        "proofs": {
            "providerPreference": {"status": "PROVEN"},
            "candidateLkgRecoveryIsolation": {"status": "PROVEN"},
            "staleReadyInvalidation": {"status": "PROVEN"},
        },
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
        "providerCount": 3,
        "activeSourceCount": 10,
        "activeMembershipCount": 12,
        "candidateProviderCount": 0,
        "approvalCandidatePresent": False,
    }


def authority() -> dict:
    return {
        "schemaVersion": 1,
        "defaultDecision": "HELD",
        "classes": {
            "builder_baseline": {
                "automationMayStage": True,
                "automationMayOpenPullRequest": True,
                "automationMayMerge": True,
                "ownerApprovalRequired": False,
                "requiredAuthority": "source-pack-autonomous-release.yml",
                "requiredGates": [
                    "farm-synchronized-manifest",
                    "exact-miyorare-pack-checks",
                    "source-pack-builder-baseline-ci",
                    "main-required-gates",
                    "protected-main-ruleset",
                ],
                "failureDecision": "HELD",
            },
            "provider_baseline": {
                "automationMayStage": True,
                "automationMayOpenPullRequest": False,
                "automationMayMerge": False,
                "ownerApprovalRequired": True,
                "requiredAuthority": "source-lab-approve-candidate.yml -> source-lab-promote-candidate.yml",
                "requiredGates": [
                    "exact-candidate-set",
                    "evidence-binding",
                    "owner-approval-proof",
                    "authorized-promotion-receipt",
                    "foundation-stale-write-check",
                ],
                "failureDecision": "HELD",
            },
            "source_onboarding": {
                "automationMayStage": True,
                "automationMayOpenPullRequest": False,
                "automationMayMerge": False,
                "ownerApprovalRequired": True,
                "requiredAuthority": "source-lab-approve-ready-sources.yml",
                "requiredGates": [
                    "ready-for-approval-state",
                    "exact-farm-state",
                    "owner-dispatch",
                    "stale-write-check",
                ],
                "failureDecision": "HELD",
            },
            "stable_release": {
                "automationMayStage": True,
                "automationMayOpenPullRequest": False,
                "automationMayMerge": False,
                "ownerApprovalRequired": False,
                "requiredAuthority": "source-pack-autonomous-release.yml -> release-source-packs.yml",
                "requiredGates": [
                    "pinned-builder-and-provider-fingerprint",
                    "compatibility-contract",
                    "immutable-version-allocation",
                    "sole-publisher",
                    "seal",
                    "post-publish-audit",
                ],
                "failureDecision": "HELD",
            },
        },
        "prohibitions": [
            "validation success alone is not promotion authority",
            "automation may not replace LKG after a failed or incomplete candidate",
            "automation may not bypass Main Required Gates",
            "no workflow other than the authoritative stable controller may allocate a stable Source Pack version",
            "no workflow other than the sole publisher may publish a stable Source Pack release",
        ],
    }


def workflows() -> dict[str, str]:
    return {
        "upstreamDetection": "\n".join([
            "schedule:",
            "Detect upstream changes against authoritative LKG",
            "Compare upstream heads with authoritative last-known-good",
            "pipeline_state = 'publish_failed'",
            "publish_recovery_available",
            "Resume exact failed provider publish",
            "MAX_RECOVERY_ATTEMPTS: '2'",
            "Dispatch fresh current-main publish recovery",
        ]),
        "runtimeValidation": "\n".join([
            "schedule:",
            "compatibility-farm-foundation",
            "activeCommit",
            "lastKnownGood",
            "source_pending_worker.py assess",
            "source_live_parser_harness.py generate",
            "--fail-threshold 3",
            "discarding stale batch state",
        ]),
        "sourceApproval": "\n".join([
            "Validate owner-only approval",
            "EXPECTED_OWNER_ID: '149634319'",
            "source_pending_approval.py plan",
            "Apply owner approval atomically",
            "Refuse stale approval commit",
            "miyorare-farm-pack-membership-sync.yml",
        ]),
        "providerPromotion": "\n".join([
            "Verify exact approval workflow run",
            "approval proof is not APPROVED",
            "approval gate fingerprint changed",
            "approval evidence binding changed",
            "Refuse promotion if foundation moved after validation",
            'entry["state"] = "RETRY"',
            '"revalidationReason"] = "PROVIDER_BASELINE_CHANGED"',
            "Emit immutable promotion receipt",
            "Revalidate PENDING sources against promoted provider baseline",
        ]),
        "lkgSafety": "\n".join([
            "Run LKG negative-regression simulations",
            "Audit authoritative LKG invariants",
            "Prove audit did not mutate Foundation",
            "A7 LKG safety verdict is not SAFE",
        ]),
        "releaseController": "\n".join([
            "Resolve approved provider fingerprint",
            "activeCommit",
            "lastKnownGood",
            '{"verify-identity", "Build Miyorare-id", "Build Miyorare-en", "Build Miyorare-Global"}',
            "source-pack-builder-baseline.yml",
            'gh pr merge "$PR_NUMBER"',
            "Resolve desired stable release fingerprint",
            "source_lab_signed",
            "gh attestation verify build/source-lab-signing-manifest.json",
            "main moved since signed controller started; retry from current main.",
            "Dispatch sole Source Pack publisher from current control plane with signed Farm snapshot",
            "release-source-packs.yml",
        ]),
        "releasePublisher": "\n".join([
            "Validate explicit Compatibility Farm release eligibility",
            "pack: [id, en]",
            "Build Miyorare-Global",
            "Verify release payload and immutable tag namespace",
            "--require-compatibility-snapshot",
            "Seal staged Source Pack draft",
            "Audit seal then publish stable release",
            "Publish audited stable release",
        ]),
        "releaseSeal": "\n".join([
            "Refuse retroactive sealing of published releases",
            "Build canonical release lock while draft",
            "Cryptographically attest release lock with GitHub OIDC",
            "gh attestation verify seal/miyorare-release-lock.json",
            "--require-sealed-before-publish",
        ]),
    }


class D4Tests(unittest.TestCase):
    def build(
        self,
        *,
        base=None,
        d3_report=None,
        d2_report=None,
        a7_report=None,
        authority_doc=None,
        workflow_texts=None,
        source_packs_base=A,
        farm=B,
        amain2=C,
    ):
        return D4.build_report(
            base or baseline(),
            d3_report or d3(),
            d2_report or d2(),
            a7_report or a7(),
            authority_doc or authority(),
            workflow_texts or workflows(),
            {
                "controlHead": D,
                "sourcePacksBase": source_packs_base,
                "compatibilityFarm": farm,
                "miyorareAmain2": amain2,
            },
        )

    def test_clean_chain_is_proven_without_mutation(self):
        report = self.build()
        self.assertEqual(report["status"], "D4_LONG_TERM_AUTOMATION_ACCEPTANCE_PROVEN")
        self.assertFalse(report["trackDClosed"])
        self.assertEqual(report["nextStage"], D4.NEXT_STAGE)
        self.assertEqual(report["proofs"]["packAndReleaseAcceptance"]["packs"], ["id", "en", "global"])
        self.assertTrue(report["proofs"]["lastKnownGoodRollbackSafety"]["status"] == "PROVEN")
        self.assertFalse(any(report["safety"].values()))

    def test_provider_promotion_cannot_become_automatic_merge(self):
        doc = deepcopy(authority())
        doc["classes"]["provider_baseline"]["automationMayMerge"] = True
        with self.assertRaisesRegex(D4.D4Error, "provider baseline owner boundary"):
            self.build(authority_doc=doc)

    def test_stale_publish_workflow_rerun_is_rejected(self):
        wf = workflows()
        wf["upstreamDetection"] += "\nactions/runs/$PUBLISH_RUN_ID/rerun"
        with self.assertRaisesRegex(D4.D4Error, "stale publish workflow snapshot"):
            self.build(workflow_texts=wf)

    def test_release_requires_global_pack(self):
        wf = workflows()
        wf["releasePublisher"] = wf["releasePublisher"].replace("Build Miyorare-Global", "")
        with self.assertRaisesRegex(D4.D4Error, "Source Pack publisher markers missing"):
            self.build(workflow_texts=wf)

    def test_a7_unsafe_fails_closed(self):
        report = deepcopy(a7())
        report["status"] = "UNSAFE"
        report["violations"] = ["LKG_MOVED"]
        with self.assertRaisesRegex(D4.D4Error, "A7 LKG safety is not SAFE"):
            self.build(a7_report=report)

    def test_d3_handoff_count_and_list_must_match(self):
        report = deepcopy(d3())
        report["operationalHandoffs"]["count"] = 2
        with self.assertRaisesRegex(D4.D4Error, "handoff metadata invalid"):
            self.build(d3_report=report)

    def test_farm_drift_fails_closed(self):
        with self.assertRaisesRegex(D4.D4Error, "Farm moved"):
            self.build(farm="e" * 40)

    def test_post_d3_base_drift_fails_closed(self):
        with self.assertRaisesRegex(D4.D4Error, "exact post-D3 main"):
            self.build(source_packs_base="e" * 40)

    def test_d2_stale_ready_proof_is_required(self):
        report = deepcopy(d2())
        del report["proofs"]["staleReadyInvalidation"]
        with self.assertRaisesRegex(D4.D4Error, "recovery proofs incomplete"):
            self.build(d2_report=report)


if __name__ == "__main__":
    unittest.main()
