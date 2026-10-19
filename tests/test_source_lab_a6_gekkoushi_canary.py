from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_lab_a6_gekkoushi_canary",
    ROOT / "tools" / "source_lab_a6_gekkoushi_canary.py",
)
assert SPEC and SPEC.loader
canary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(canary)

SHA = "a" * 40
CANDIDATE = "b" * 40
NEW_SHA = "c" * 40
WORKFLOW = ROOT / ".github" / "workflows" / "source-lab-a6-gekkoushi-canary.yml"


def status(*, active: str = SHA, lkg: str = SHA, current: str = SHA, candidate: str = CANDIDATE) -> dict:
    return {
        "providers": {
            "gekkoushi": {
                "activeCommit": active,
                "lastKnownGood": lkg,
            }
        },
        "automation": {
            "candidates": {
                "gekkoushi": {
                    "current": current,
                    "candidate": candidate,
                }
            }
        },
    }


def registry() -> dict:
    return {
        "sources": [
            {"canonicalId": "en-a", "language": "en"},
            {"canonicalId": "en-b", "language": "en"},
            {"canonicalId": "id-a", "language": "id"},
            {"canonicalId": "id-b", "language": "id"},
            {"canonicalId": "repair", "language": "en"},
        ]
    }


def parser_plan() -> dict:
    def row(canonical_id: str, recipes: list[str] | None = None) -> dict:
        return {
            "provider": "gekkoushi",
            "familyId": f"family-{canonical_id}",
            "registryAdapterFamily": "native",
            "providerParserFamily": "native",
            "runner": "gradle",
            "canonicalId": canonical_id,
            "testClass": f"compatibilityfarm.AutoLive_{canonical_id.replace('-', '_')}",
            "runtimeProfile": "common",
            "repairRecipes": recipes or [],
        }

    return {
        "provider": "gekkoushi",
        "include": [
            row("en-a"),
            row("en-b"),
            row("id-a"),
            row("id-b"),
            row("repair", ["forward-parser-request-headers-to-http-get"]),
        ],
    }


def aggregate(statuses: dict[str, str]) -> dict:
    return {
        "results": [
            {
                "canonicalId": canonical_id,
                "providerExecutions": [
                    {"provider": "gekkoushi", "status": state}
                ],
            }
            for canonical_id, state in statuses.items()
        ]
    }


class SourceLabA6PlannerTests(unittest.TestCase):
    def test_plan_is_balanced_bounded_and_excludes_repair_memberships(self) -> None:
        result = canary.select_canary_memberships(registry(), parser_plan(), status(), 4)
        self.assertEqual("A6_GEKKOUSHI_CANARY", result["phase"])
        self.assertEqual(SHA, result["lastKnownGood"])
        self.assertEqual(CANDIDATE, result["candidate"])
        self.assertEqual(4, result["membershipCount"])
        selected = result["include"]
        self.assertEqual({"en", "id"}, {row["language"] for row in selected})
        self.assertNotIn("repair", {row["canonicalId"] for row in selected})
        self.assertTrue(all(row["repairRecipes"] == [] for row in selected))

    def test_plan_refuses_non_lkg_active_baseline(self) -> None:
        with self.assertRaisesRegex(canary.CanaryError, "active commit must equal"):
            canary.select_canary_memberships(
                registry(), parser_plan(), status(active=NEW_SHA), 4
            )

    def test_plan_refuses_candidate_not_based_on_lkg(self) -> None:
        with self.assertRaisesRegex(canary.CanaryError, "candidate baseline must equal"):
            canary.select_canary_memberships(
                registry(), parser_plan(), status(current=NEW_SHA), 4
            )

    def test_mixed_pass_fail_canary_is_accepted_when_isolated_and_lkg_unchanged(self) -> None:
        plan = canary.select_canary_memberships(registry(), parser_plan(), status(), 4)
        ids = [row["canonicalId"] for row in plan["include"]]
        states = {canonical_id: ("FAIL" if i == 0 else "PASS") for i, canonical_id in enumerate(ids)}
        verdict, accepted = canary.build_verdict(plan, aggregate(states), status(), SHA)
        self.assertTrue(accepted)
        self.assertTrue(verdict["allCanaryMembershipsExecuted"])
        self.assertTrue(verdict["isolatedFailureEvidencePreserved"])
        self.assertFalse(verdict["canaryAllPassed"])
        self.assertTrue(verdict["lastKnownGoodUnchanged"])
        self.assertFalse(verdict["promotionAttempted"])

    def test_verdict_refuses_remote_lkg_drift(self) -> None:
        plan = canary.select_canary_memberships(registry(), parser_plan(), status(), 2)
        states = {row["canonicalId"]: "PASS" for row in plan["include"]}
        remote = status(active=NEW_SHA, lkg=NEW_SHA, current=NEW_SHA, candidate=CANDIDATE)
        verdict, accepted = canary.build_verdict(plan, aggregate(states), remote, SHA)
        self.assertFalse(accepted)
        self.assertFalse(verdict["lastKnownGoodUnchanged"])

    def test_verdict_refuses_all_fail_canary(self) -> None:
        plan = canary.select_canary_memberships(registry(), parser_plan(), status(), 2)
        states = {row["canonicalId"]: "FAIL" for row in plan["include"]}
        verdict, accepted = canary.build_verdict(plan, aggregate(states), status(), SHA)
        self.assertFalse(accepted)
        self.assertFalse(verdict["atLeastOneCanaryPassed"])


class SourceLabA6WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_read_only_owner_replay_and_same_repo_pr_only(self) -> None:
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("pull_request:", self.text)
        self.assertIn("EXPECTED_OWNER_ID: '149634319'", self.text)
        self.assertIn("contents: read", self.text)
        self.assertNotIn("contents: write", self.text)
        self.assertIn("PR_HEAD_REPO", self.text)
        self.assertIn("same-repository", self.text)
        self.assertNotIn("git push", self.text)

    def test_memberships_are_isolated_non_fail_fast_and_exact_test_scoped(self) -> None:
        self.assertIn("fail-fast: false", self.text)
        self.assertIn("max-parallel: 4", self.text)
        self.assertIn("--tests \"$TEST_CLASS\"", self.text)
        self.assertIn("continue-on-error: true", self.text)
        self.assertIn("isolated report must contain exactly one membership", self.text)

    def test_canary_derives_candidate_from_authoritative_foundation(self) -> None:
        self.assertIn("compatibility-farm-foundation", self.text)
        self.assertIn("source_lab_a6_gekkoushi_canary.py plan", self.text)
        self.assertIn("--status farm/upstream/status.json", self.text)
        self.assertNotIn("12cd1faa0d5a9f846a048fbb9c7d79328c0f1e67", self.text)

    def test_aggregate_rechecks_remote_lkg_and_never_promotes(self) -> None:
        self.assertIn("remote-status.json", self.text)
        self.assertIn("source_lab_a6_gekkoushi_canary.py verdict", self.text)
        self.assertIn("lastKnownGoodUnchanged", self.text)
        self.assertIn("promotionAttempted", self.text)
        self.assertNotIn("source-lab-promote-candidate", self.text)
        self.assertNotIn("candidate_lifecycle.py", self.text)


if __name__ == "__main__":
    unittest.main()
