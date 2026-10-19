from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import source_lab_b3_reconciliation as reconciliation
import source_lab_b3_runtime_closure as closure


RUNTIME_IDS = [
    "FIRESCANS",
    "HEYTOON",
    "KALISCAN",
    "MANHWA18ORG",
    "NOVELCROW",
    "PAWMANGA",
    "SHIBAMANGA",
    "WHALEMANGA",
    "WOOPREAD",
]


def row(name: str, decision: str, same: bool = False):
    providers = {}
    if decision == reconciliation.RUNTIME_UNRESOLVED:
        providers = {"gekkoushi": {"state": "BOTH_RUNTIME_FAILING", "sameRuntimeFailure": same}}
    return {
        "canonicalId": f"miyorare:inventory-en:{name}",
        "displayName": name,
        "b3Decision": decision,
        "nextPhase": "TRACK_B_BATCH_3",
        "providers": providers,
        "safety": {"readOnly": True},
    }


def boundary():
    rows = [row(name, reconciliation.RUNTIME_UNRESOLVED, same=True) for name in RUNTIME_IDS]
    rows.extend(row(f"FILL{i:02d}", reconciliation.PRIMARY_MISSING) for i in range(24))
    return {"readOnly": True, "source": {"head": "frozen"}, "rows": rows}


def upstream_evidence():
    return {
        "schemaVersion": 1,
        "phase": reconciliation.PHASE,
        "readOnly": True,
        "entries": [],
    }


def live_evidence():
    dispositions = {
        "NOVELCROW": "WAF_BLOCKED",
        "WHALEMANGA": "WAF_BLOCKED",
        "WOOPREAD": "WAF_BLOCKED",
        "PAWMANGA": "DOMAIN_PARKED_OR_REDIRECTED",
        "FIRESCANS": "DNS_UNRESOLVED",
        "HEYTOON": "DNS_UNRESOLVED",
        "KALISCAN": "DNS_UNRESOLVED",
        "MANHWA18ORG": "TLS_UNREACHABLE",
        "SHIBAMANGA": "DNS_UNRESOLVED",
    }
    return {
        "schemaVersion": 1,
        "phase": closure.LIVE_PHASE,
        "readOnly": True,
        "source": {
            "pr": 160,
            "head": "a" * 40,
            "runId": 1,
            "artifactId": 2,
            "artifactDigest": "sha256:" + "b" * 64,
            "probeWorkflowBlob": "c" * 40,
        },
        "entries": [
            {
                "canonicalId": f"miyorare:inventory-en:{name}",
                "disposition": dispositions[name],
                "observations": ["current live observation"],
            }
            for name in RUNTIME_IDS
        ],
    }


class RuntimeClosureTest(unittest.TestCase):
    def test_live_evidence_closes_parser_repair_routes(self):
        report = closure.build_report(boundary(), upstream_evidence(), live_evidence())
        self.assertEqual(report["summary"]["rows"], 33)
        self.assertEqual(report["summary"]["liveAccessEvidenceBackedRows"], 9)
        self.assertEqual(report["summary"]["routes"]["LIVE_ACCESS_BLOCKED"], 8)
        self.assertEqual(report["summary"]["routes"]["LIVE_DOMAIN_DISPOSITION"], 1)
        self.assertEqual(report["summary"]["routes"]["PRIMARY_MISSING_UNRESOLVED"], 24)
        self.assertNotIn("SHARED_RUNTIME_FAILURE", report["summary"]["routes"])
        self.assertNotIn("RUNTIME_FAILURE_DIVERGED", report["summary"]["routes"])
        self.assertFalse(report["safety"]["mutatesAuthority"])
        self.assertFalse(report["safety"]["approvesOverlay"])

    def test_runtime_evidence_must_cover_exact_nine_source_cohort(self):
        live = live_evidence()
        live["entries"].pop()
        with self.assertRaises(ValueError):
            closure.validate_live_access_evidence(boundary(), live)

    def test_runtime_evidence_cannot_target_primary_missing_row(self):
        live = live_evidence()
        live["entries"][0]["canonicalId"] = "miyorare:inventory-en:FILL00"
        with self.assertRaises(ValueError):
            closure.validate_live_access_evidence(boundary(), live)

    def test_unknown_disposition_fails_closed(self):
        live = live_evidence()
        live["entries"][0]["disposition"] = "PARSER_BROKEN"
        with self.assertRaises(ValueError):
            closure.validate_live_access_evidence(boundary(), live)

    def test_provenance_metadata_is_required(self):
        live = live_evidence()
        live["source"]["artifactDigest"] = "not-a-digest"
        with self.assertRaises(ValueError):
            closure.validate_live_access_evidence(boundary(), live)


if __name__ == "__main__":
    unittest.main()
