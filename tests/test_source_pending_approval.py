#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_pending_approval", ROOT / "tools" / "source_pending_approval.py"
)
assert SPEC and SPEC.loader
approval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(approval)


SHA = "a" * 40


def registry() -> dict:
    return {
        "schemaVersion": 1,
        "providerBaselines": {"uma": SHA},
        "sources": [
            {
                "canonicalId": "miyorare:inventory-en:EXAMPLE",
                "language": "en",
                "providers": ["uma"],
                "currentVersion": {"uma": SHA},
                "lastKnownGood": {"uma": SHA},
                "healthyHistory": [],
                "authType": "UNSUPPORTED",
                "adapterFamily": "unclassified",
                "runtimeHealth": "UNKNOWN",
                "ownerActionRequired": False,
                "publishEligible": False,
                "selectionReasons": ["automatic-source-inventory"],
                "compatibilityEnrollment": {
                    "state": "PENDING",
                    "parserCoverageRequired": False,
                },
            }
        ],
    }


def ready_state() -> dict:
    evidence = {
        "attempts": 1,
        "profile": {
            "gate": "PASS",
            "memberships": [
                {
                    "provider": "uma",
                    "profilePass": True,
                    "compile": True,
                    "probe": {"reachable": True},
                }
            ],
        },
        "parser": {
            "executionMode": "real-live-parser",
            "gate": "PASS",
            "memberships": [
                {
                    "canonicalId": "miyorare:inventory-en:EXAMPLE",
                    "provider": "uma",
                    "status": "PASS",
                    "parserExecution": True,
                    "detailsTraversal": True,
                    "chapterTraversal": True,
                    "pageExtraction": True,
                }
            ],
        },
        "gate": "REAL_PARSER_PASS",
    }
    return {
        "schemaVersion": 2,
        "sources": {
            "miyorare:inventory-en:EXAMPLE": {
                "schemaVersion": 2,
                "state": "READY_FOR_APPROVAL",
                "approvalState": "WAITING_FOR_APPROVAL",
                "attempts": 1,
                "workflowRunId": "123",
                "adapterFamily": "madara",
                "authType": "NO_AUTH",
                "testedVersions": {"uma": SHA},
                "evidence": evidence,
                "evidenceSha256": approval.digest(evidence),
                "publishEligible": False,
            }
        },
    }


class SourcePendingApprovalTest(unittest.TestCase):
    def test_plan_accepts_only_real_parser_bound_ready_source(self) -> None:
        value = approval.plan(registry(), ready_state())
        self.assertEqual(value["count"], 1)
        item = value["sources"][0]
        self.assertEqual(item["canonicalId"], "miyorare:inventory-en:EXAMPLE")
        self.assertEqual(item["testedVersions"], {"uma": SHA})

    def test_plan_rejects_stale_provider_version(self) -> None:
        reg = registry()
        reg["providerBaselines"]["uma"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "provider baseline moved"):
            approval.plan(reg, ready_state())

    def test_plan_rejects_fake_real_parser_gate(self) -> None:
        state = ready_state()
        entry = state["sources"]["miyorare:inventory-en:EXAMPLE"]
        entry["evidence"]["parser"]["memberships"][0]["pageExtraction"] = False
        entry["evidenceSha256"] = approval.digest(entry["evidence"])
        with self.assertRaisesRegex(ValueError, "parser traversal incomplete"):
            approval.plan(registry(), state)

    def test_apply_activates_source_and_marks_worker_approved(self) -> None:
        reg = registry()
        state = ready_state()
        plan = approval.plan(reg, state)
        updated_reg, updated_state, receipt = approval.apply(
            reg,
            state,
            copy.deepcopy(plan),
            "Noirero:149634319",
            "2026-09-18T01:00:00Z",
            "999",
        )
        source = updated_reg["sources"][0]
        self.assertEqual(source["compatibilityEnrollment"], {
            "state": "ACTIVE",
            "parserCoverageRequired": True,
        })
        self.assertEqual(source["authType"], "NO_AUTH")
        self.assertEqual(source["adapterFamily"], "madara")
        self.assertEqual(source["runtimeHealth"], "HEALTHY")
        self.assertIn(SHA, source["healthyHistory"])
        self.assertEqual(source["onboardingApproval"]["state"], "APPROVED")
        entry = updated_state["sources"]["miyorare:inventory-en:EXAMPLE"]
        self.assertEqual(entry["state"], "APPROVED")
        self.assertEqual(entry["approvalState"], "APPROVED")
        self.assertEqual(receipt["count"], 1)
        self.assertFalse(receipt["publishEligible"])

    def test_apply_rejects_stale_plan(self) -> None:
        reg = registry()
        state = ready_state()
        plan = approval.plan(reg, state)
        plan["sources"][0]["adapterFamily"] = "tampered"
        with self.assertRaisesRegex(ValueError, "approval plan changed"):
            approval.apply(
                reg,
                state,
                plan,
                "Noirero:149634319",
                "2026-09-18T01:00:00Z",
                "999",
            )


if __name__ == "__main__":
    unittest.main()
