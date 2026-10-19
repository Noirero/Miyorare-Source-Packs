#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_held_observability", ROOT / "tools" / "source_held_observability.py")
assert SPEC and SPEC.loader
held = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(held)

SHA = "a" * 40
OLD_SHA = "b" * 40
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def registry(*sources: dict, baseline: str = SHA) -> dict:
    return {"providerBaselines": {"gekkoushi": baseline}, "sources": list(sources)}


def source(canonical_id: str = "alpha") -> dict:
    return {
        "canonicalId": canonical_id,
        "language": "en",
        "providers": ["gekkoushi"],
        "compatibilityEnrollment": {"state": "PENDING"},
    }


def permanent_entry(*, tested: str = SHA, annotated: bool = False, reason: str = "Original site closed") -> dict:
    value = {
        "state": held.HELD,
        "attempts": 2,
        "lastCheckedAt": "2026-10-19T10:00:00Z",
        "testedVersions": {"gekkoushi": tested},
        "ownerActionRequired": False,
        "evidence": {
            "attempts": 2,
            "profile": {
                "gate": "FAIL",
                "memberships": [
                    {
                        "provider": "gekkoushi",
                        "profilePass": False,
                        "upstreamBrokenReason": reason,
                        "probe": {"reachable": False, "detail": "upstream-declared-broken"},
                    }
                ],
            },
        },
    }
    if annotated:
        value["failureCategory"] = "PERMANENT_UPSTREAM"
        value["holdReason"] = "TERMINAL_EVIDENCE"
    return value


class HeldObservabilityTest(unittest.TestCase):
    def test_current_closed_site_hold_is_policy_consistent(self) -> None:
        report = held.audit(registry(source()), {"sources": {"alpha": permanent_entry(annotated=True)}}, NOW)
        row = report["heldEntries"][0]
        self.assertEqual("PERMANENT_UPSTREAM", row["effectiveCategory"])
        self.assertEqual("SITE_CLOSED_OR_GONE", row["operationalReasonClass"])
        self.assertEqual("CURRENT", row["evidenceBindingStatus"])
        self.assertEqual("KEEP_HELD_SITE_UNAVAILABLE", row["reviewDisposition"])
        self.assertTrue(row["policyConsistentCurrentHold"])
        self.assertFalse(row["reviewRequired"])

    def test_fixable_parser_reason_is_visible_without_mutating_lifecycle_category(self) -> None:
        entry = permanent_entry(reason="Site is online but parser is broken — layout/API changed, needs rewrite")
        report = held.audit(registry(source()), {"sources": {"alpha": entry}}, NOW)
        row = report["heldEntries"][0]
        self.assertEqual("PERMANENT_UPSTREAM", row["effectiveCategory"])
        self.assertEqual("PARSER_REWRITE_REQUIRED", row["operationalReasonClass"])
        self.assertEqual("REVIEW_FIXABLE_PARSER_HOLD", row["reviewDisposition"])
        self.assertTrue(row["policyConsistentCurrentHold"])
        self.assertTrue(row["operationallyReviewableCurrentHold"])
        self.assertTrue(row["reviewRequired"])

    def test_stale_terminal_hold_is_visible_for_revalidation(self) -> None:
        report = held.audit(registry(source()), {"sources": {"alpha": permanent_entry(tested=OLD_SHA)}}, NOW)
        row = report["heldEntries"][0]
        self.assertEqual("STALE", row["evidenceBindingStatus"])
        self.assertEqual("REVALIDATE_STALE_TERMINAL_EVIDENCE", row["reviewDisposition"])
        self.assertTrue(row["reviewRequired"])

    def test_legacy_nonterminal_parser_hold_is_review_only(self) -> None:
        entry = {
            "state": held.HELD,
            "attempts": 3,
            "lastCheckedAt": "2026-10-19T10:00:00Z",
            "testedVersions": {"gekkoushi": SHA},
            "evidence": {
                "parser": {
                    "gate": "FAIL",
                    "memberships": [
                        {
                            "provider": "gekkoushi",
                            "status": "FAIL",
                            "parserExecution": True,
                            "failures": 1,
                            "failureType": "AssertionError",
                            "failureMessage": "details traversal failed",
                        }
                    ],
                }
            },
        }
        report = held.audit(registry(source()), {"sources": {"alpha": entry}}, NOW)
        row = report["heldEntries"][0]
        self.assertEqual("SOURCE_PARSER_FAILURE", row["effectiveCategory"])
        self.assertEqual("SOURCE_PARSER_FAILURE", row["operationalReasonClass"])
        self.assertEqual("REVIEW_NONTERMINAL_OR_UNKNOWN_HOLD", row["reviewDisposition"])
        self.assertTrue(row["reviewRequired"])
        self.assertFalse(row["policyConsistentCurrentHold"])

    def test_missing_baseline_binding_is_not_silently_current(self) -> None:
        entry = permanent_entry()
        entry.pop("testedVersions")
        report = held.audit(registry(source()), {"sources": {"alpha": entry}}, NOW)
        row = report["heldEntries"][0]
        self.assertEqual("MISSING_TESTED_VERSIONS", row["evidenceBindingStatus"])
        self.assertEqual("REVALIDATE_STALE_TERMINAL_EVIDENCE", row["reviewDisposition"])
        self.assertEqual(1, report["summary"]["incompleteOrMismatchedEvidence"])

    def test_category_conflict_is_never_treated_as_consistent(self) -> None:
        entry = permanent_entry(annotated=True)
        entry["failureCategory"] = "AUTH_REQUIRED"
        report = held.audit(registry(source()), {"sources": {"alpha": entry}}, NOW)
        row = report["heldEntries"][0]
        self.assertFalse(row["categoryAgreement"])
        self.assertEqual("REVIEW_CATEGORY_CONFLICT", row["reviewDisposition"])
        self.assertFalse(row["policyConsistentCurrentHold"])


if __name__ == "__main__":
    unittest.main()
