from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("b3r", ROOT / "tools" / "source_lab_b3_reconciliation.py")
b3r = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(b3r)


def safety():
    return {"readOnly": True}


def boundary(rows):
    return {"readOnly": True, "source": {"head": "h"}, "rows": rows}


def row(cid, decision, providers=None):
    return {
        "canonicalId": cid,
        "displayName": cid.rsplit(":", 1)[-1],
        "b3Decision": decision,
        "nextPhase": "TRACK_B_BATCH_3",
        "providers": providers or {},
        "safety": safety(),
    }


def padded(rows):
    values = list(rows)
    while len(values) < 33:
        i = len(values)
        values.append(row(f"miyorare:inventory-en:FILL{i:02d}", b3r.PRIMARY_MISSING))
    return boundary(values)


def evidence(entries):
    return {"schemaVersion": 1, "phase": b3r.PHASE, "readOnly": True, "entries": entries}


class ReconciliationTest(unittest.TestCase):
    def test_dead_evidence_routes_without_repair(self):
        cid = "miyorare:inventory-en:DEAD"
        b = padded([row(cid, b3r.PRIMARY_MISSING)])
        e = evidence([{"canonicalId": cid, "disposition": "UPSTREAM_DEAD", "commit": "a" * 40,
                       "proof": [{"type": "commit_message_contains", "value": "dead"}]}])
        report = b3r.build_report(b, e)
        item = next(x for x in report["decisions"] if x["canonicalId"] == cid)
        self.assertEqual(item["route"], "PROVEN_UPSTREAM_DEAD")
        self.assertEqual(item["nextAction"], "NO_PRIMARY_REPAIR_WITHOUT_NEW_REPLACEMENT_EVIDENCE")
        self.assertFalse(item["safety"]["mutateLastKnownGood"])

    def test_locale_migration_is_not_dead(self):
        cid = "miyorare:inventory-en:MOVED"
        b = padded([row(cid, b3r.PRIMARY_MISSING)])
        e = evidence([{"canonicalId": cid, "disposition": "UPSTREAM_LOCALE_MIGRATION", "commit": "b" * 40,
                       "proof": [{"type": "commit_message_contains", "value": "moved"}]}])
        item = next(x for x in b3r.build_report(b, e)["decisions"] if x["canonicalId"] == cid)
        self.assertEqual(item["route"], "PROVEN_UPSTREAM_MIGRATION")
        self.assertEqual(item["nextAction"], "B3_TARGETED_REPLACEMENT_IDENTITY_RECONCILIATION")

    def test_missing_without_evidence_stays_unresolved(self):
        cid = "miyorare:inventory-en:UNKNOWN"
        item = next(x for x in b3r.build_report(padded([row(cid, b3r.PRIMARY_MISSING)]), evidence([]))["decisions"] if x["canonicalId"] == cid)
        self.assertEqual(item["route"], "PRIMARY_MISSING_UNRESOLVED")

    def test_profile_blocked_routes_to_network_recheck(self):
        cid = "miyorare:inventory-en:NET"
        providers = {"gekkoushi": {"state": "BOTH_PROFILE_BLOCKED", "sameRuntimeFailure": False}}
        item = next(x for x in b3r.build_report(padded([row(cid, b3r.RUNTIME_UNRESOLVED, providers)]), evidence([]))["decisions"] if x["canonicalId"] == cid)
        self.assertEqual(item["route"], "NETWORK_OR_PROFILE_BLOCKED")

    def test_shared_runtime_failure_routes_to_parser_repair(self):
        cid = "miyorare:inventory-en:PARSER"
        providers = {"gekkoushi": {"state": "BOTH_RUNTIME_FAILING", "sameRuntimeFailure": True}}
        item = next(x for x in b3r.build_report(padded([row(cid, b3r.RUNTIME_UNRESOLVED, providers)]), evidence([]))["decisions"] if x["canonicalId"] == cid)
        self.assertEqual(item["route"], "SHARED_RUNTIME_FAILURE")
        self.assertEqual(item["nextAction"], "B3_TARGETED_PARSER_REPAIR")

    def test_candidate_regression_wins(self):
        cid = "miyorare:inventory-en:REG"
        providers = {"uma": {"state": "CANDIDATE_REGRESSION", "sameRuntimeFailure": False}}
        item = next(x for x in b3r.build_report(padded([row(cid, b3r.RUNTIME_UNRESOLVED, providers)]), evidence([]))["decisions"] if x["canonicalId"] == cid)
        self.assertEqual(item["route"], "CANDIDATE_REGRESSION")

    def test_duplicate_or_outside_evidence_fails_closed(self):
        cid = "miyorare:inventory-en:A"
        b = padded([row(cid, b3r.PRIMARY_MISSING)])
        base = {"canonicalId": cid, "disposition": "UPSTREAM_DEAD", "commit": "a" * 40,
                "proof": [{"type": "commit_message_contains", "value": "x"}]}
        with self.assertRaises(ValueError):
            b3r.validate_evidence(b, evidence([base, dict(base)]))
        outside = dict(base)
        outside["canonicalId"] = "miyorare:inventory-en:OUTSIDE"
        with self.assertRaises(ValueError):
            b3r.validate_evidence(b, evidence([outside]))

    def test_boundary_requires_exact_33(self):
        with self.assertRaises(ValueError):
            b3r.boundary_rows(boundary([row("x", b3r.PRIMARY_MISSING)]))


if __name__ == "__main__":
    unittest.main()
