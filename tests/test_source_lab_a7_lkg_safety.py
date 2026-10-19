import copy
import importlib
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from source_lab_a7_lkg_safety import audit_lkg_safety

OLD = "1" * 40
NEW = "2" * 40
DRIFT = "3" * 40
D64 = "a" * 64


def workflow_contract() -> str:
    return "\n".join([
        "EXPECTED_OWNER_ID: '149634319'",
        '[[ "$GITHUB_ACTOR_ID" == "$EXPECTED_OWNER_ID" ]]',
        '"conclusion": "success"',
        '"path": ".github/workflows/source-lab-approve-candidate.yml"',
        "live candidateSetId changed; promotion is stale",
        "candidate is no longer waiting for approval",
        "approval evidence binding changed",
        "approved provider SHAs do not match live candidate",
        "approval sourceScope changed",
        "compatibility baseline moved",
        "source state moved",
        "active/LKG moved",
        "Refuse promotion if foundation moved after validation",
        "git -C farm fetch origin compatibility-farm-foundation",
        "git -C farm push origin HEAD:compatibility-farm-foundation",
    ])


def safe_documents():
    upstream = {
        "schema": 1,
        "policy": {"keepLastKnownGoodOnFailure": True, "perSourceFailSafe": True},
        "providers": {"gekkoushi": {"upstreamBase": OLD, "lastKnownGood": OLD}},
    }
    status = {
        "schema": 3,
        "providers": {"gekkoushi": {"activeCommit": OLD, "lastKnownGood": OLD}},
        "automation": {
            "candidates": {"gekkoushi": {"current": OLD, "candidate": NEW}},
        },
    }
    registry = {
        "providerBaselines": {"gekkoushi": OLD},
        "sources": [{
            "canonicalId": "miyorare:test:ONE",
            "providers": ["gekkoushi"],
            "compatibilityEnrollment": {"state": "ACTIVE", "parserCoverageRequired": True},
            "currentVersion": {"gekkoushi": OLD},
            "lastKnownGood": {"gekkoushi": OLD},
        }],
    }
    return upstream, status, registry


class A7AuditTests(unittest.TestCase):
    def test_safe_provider_candidate_and_active_source(self):
        upstream, status, registry = safe_documents()
        report = audit_lkg_safety(upstream, status, registry, workflow_contract())
        self.assertEqual("SAFE", report["status"], report["violations"])
        self.assertEqual(1, report["activeMembershipCount"])
        self.assertFalse(report["mutatesFoundation"])
        self.assertFalse(report["promotionAttempted"])

    def test_candidate_baseline_drift_fails_closed(self):
        upstream, status, registry = safe_documents()
        status["automation"]["candidates"]["gekkoushi"]["current"] = DRIFT
        report = audit_lkg_safety(upstream, status, registry, workflow_contract())
        self.assertEqual("UNSAFE", report["status"])
        self.assertTrue(any("candidate baseline is stale" in item for item in report["violations"]))

    def test_active_and_lkg_divergence_is_unsafe(self):
        upstream, status, registry = safe_documents()
        status["providers"]["gekkoushi"]["activeCommit"] = NEW
        report = audit_lkg_safety(upstream, status, registry, workflow_contract())
        self.assertTrue(any("activeCommit != runtime lastKnownGood" in item for item in report["violations"]))

    def test_active_source_current_and_lkg_divergence_is_unsafe(self):
        upstream, status, registry = safe_documents()
        registry["sources"][0]["currentVersion"]["gekkoushi"] = NEW
        report = audit_lkg_safety(upstream, status, registry, workflow_contract())
        self.assertTrue(any("currentVersion != lastKnownGood" in item for item in report["violations"]))

    def test_promotion_push_must_follow_stale_foundation_check(self):
        upstream, status, registry = safe_documents()
        workflow = workflow_contract().replace(
            "Refuse promotion if foundation moved after validation\ngit -C farm fetch origin compatibility-farm-foundation\ngit -C farm push origin HEAD:compatibility-farm-foundation",
            "git -C farm push origin HEAD:compatibility-farm-foundation\nRefuse promotion if foundation moved after validation\ngit -C farm fetch origin compatibility-farm-foundation",
        )
        report = audit_lkg_safety(upstream, status, registry, workflow)
        self.assertTrue(any("stale Foundation check must occur before promotion push" in item for item in report["violations"]))


FARM_ROOT = Path(os.environ.get("FARM_ROOT", "")) if os.environ.get("FARM_ROOT") else None
FOUNDATION_TOOLS_AVAILABLE = bool(FARM_ROOT and (FARM_ROOT / "tools/approval_state.py").is_file())


@unittest.skipUnless(FOUNDATION_TOOLS_AVAILABLE, "authoritative Foundation tools not provided")
class A7FoundationNegativeSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(FARM_ROOT / "tools"))
        cls.approval_state = importlib.import_module("approval_state")
        cls.candidate_lifecycle = importlib.import_module("candidate_lifecycle")
        cls.authorized_promotion = importlib.import_module("authorized_promotion")

    def make_pending(self):
        registry = {"providers": {"gekkoushi": {"lastKnownGood": OLD}}}
        plan = {
            "schema": 1,
            "providers": {"gekkoushi": {"changed": True, "lastKnownGood": OLD, "candidate": NEW}},
        }
        gate = {
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
        binding = {
            "schemaVersion": 1,
            "farmEvidenceSha256": D64,
            "gateSha256": "b" * 64,
            "repairEvidenceSha256": "c" * 64,
            "repairEvidenceCount": 0,
        }
        pending = self.approval_state.build_pending(registry, plan, gate, binding)
        approval = self.approval_state.approve_pending(pending, pending["candidateSetId"], "Noirero:149634319")
        return registry, pending, approval

    def test_staging_candidate_never_moves_active_or_lkg(self):
        _, pending, _ = self.make_pending()
        status = {
            "schema": 3,
            "providers": {"gekkoushi": {"activeCommit": OLD, "lastKnownGood": OLD, "runtimeHealth": "DEGRADED"}},
        }
        staged = self.candidate_lifecycle.stage_waiting(status, pending)
        self.assertEqual(OLD, staged["providers"]["gekkoushi"]["activeCommit"])
        self.assertEqual(OLD, staged["providers"]["gekkoushi"]["lastKnownGood"])
        self.assertEqual(NEW, staged["providers"]["gekkoushi"]["candidate"]["commit"])

    def test_held_candidate_never_moves_active_or_lkg(self):
        _, pending, _ = self.make_pending()
        status = {
            "schema": 3,
            "approvalCandidate": pending,
            "providers": {"gekkoushi": {"activeCommit": OLD, "lastKnownGood": OLD, "runtimeHealth": "DEGRADED"}},
        }
        held = self.candidate_lifecycle.hold_candidate(status, "gekkoushi", NEW, "REAL_PARSER_FAILURE")
        self.assertEqual(OLD, held["providers"]["gekkoushi"]["activeCommit"])
        self.assertEqual(OLD, held["providers"]["gekkoushi"]["lastKnownGood"])
        self.assertNotIn("approvalCandidate", held)

    def test_authorization_rejects_registry_lkg_drift(self):
        registry, pending, approval = self.make_pending()
        drifted = copy.deepcopy(registry)
        drifted["providers"]["gekkoushi"]["lastKnownGood"] = DRIFT
        with self.assertRaises(self.approval_state.ApprovalStateError):
            self.approval_state.authorize_promotion(drifted, pending, approval, "gekkoushi", NEW)

    def test_authorized_promotion_rejects_post_authorization_lkg_drift(self):
        registry, pending, approval = self.make_pending()
        authorization = self.approval_state.authorize_promotion(
            registry, pending, approval, "gekkoushi", NEW
        )
        drifted = copy.deepcopy(registry)
        drifted["providers"]["gekkoushi"]["lastKnownGood"] = DRIFT
        with self.assertRaises(self.authorized_promotion.AuthorizedPromotionError):
            self.authorized_promotion.apply_authorized_promotion(
                drifted, authorization, "gekkoushi", NEW
            )


if __name__ == "__main__":
    unittest.main()
