from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import source_lab_b3_identity_closure as closure
import source_lab_b3_runtime_closure as runtime_closure


BOUNDARY = ROOT / "compatibility/evidence/track-b-batch3-runtime-boundary.json"
UPSTREAM = ROOT / "compatibility/evidence/track-b-batch3-upstream-disposition.json"
LIVE = ROOT / "compatibility/evidence/track-b-batch3-live-runtime-access.json"
IDENTITY = ROOT / "compatibility/evidence/track-b-batch3-identity-closure.json"


class IdentityClosureTest(unittest.TestCase):
    def setUp(self):
        self.boundary = runtime_closure.load_json(BOUNDARY)
        self.upstream = runtime_closure.load_json(UPSTREAM)
        self.live = runtime_closure.load_json(LIVE)
        self.identity = runtime_closure.load_json(IDENTITY)

    def build(self, identity=None):
        return closure.build_report(
            self.boundary,
            self.upstream,
            self.live,
            self.identity if identity is None else identity,
        )

    def test_actual_batch3_evidence_closes_all_33_rows(self):
        report = self.build()
        self.assertEqual(report["summary"]["rows"], 33)
        self.assertEqual(report["summary"]["runtimeClosureEvidenceBackedRows"], 25)
        self.assertEqual(report["summary"]["identityEvidenceRows"], 9)
        self.assertEqual(report["summary"]["newlyClosedPrimaryMissingRows"], 8)
        self.assertEqual(report["summary"]["evidenceBackedRows"], 33)
        self.assertEqual(
            report["summary"]["routes"],
            {
                "LIVE_ACCESS_BLOCKED": 8,
                "LIVE_DOMAIN_DISPOSITION": 1,
                "PROVEN_UPSTREAM_DEAD": 23,
                "PROVEN_UPSTREAM_MIGRATION": 1,
            },
        )
        self.assertNotIn("PRIMARY_MISSING_UNRESOLVED", report["summary"]["routes"])

    def test_dead_removals_are_not_promoted_to_primary_replacements(self):
        report = self.build()
        closed = [
            row for row in report["decisions"]
            if row.get("identityClosureEvidence", {}).get("disposition") == closure.DEAD
        ]
        self.assertEqual(len(closed), 8)
        for row in closed:
            self.assertEqual(row["route"], "PROVEN_UPSTREAM_DEAD")
            self.assertEqual(
                row["nextAction"],
                "NO_PRIMARY_REPAIR_WITHOUT_NEW_REPLACEMENT_EVIDENCE",
            )
            self.assertEqual(row["identityClosureEvidence"]["farmIdentity"]["provider"], "keiyoushi")

    def test_cmanhua_stays_migration_and_reference_only(self):
        report = self.build()
        row = next(item for item in report["decisions"] if item["canonicalId"] == closure.CMANHUA)
        self.assertEqual(row["route"], "PROVEN_UPSTREAM_MIGRATION")
        self.assertEqual(
            row["nextAction"],
            "NO_EN_PRIMARY_REPAIR_PRESERVE_REFERENCE_ONLY_MIGRATION",
        )
        proof = row["identityClosureEvidence"]["proof"]
        self.assertEqual(proof["targetModule"], "src/zh/cmanhua")
        self.assertEqual(proof["targetLanguage"], "zh")
        self.assertEqual(proof["targetPackageName"], "en.cmanhua")

    def test_missing_identity_entry_fails_closed(self):
        evidence = copy.deepcopy(self.identity)
        evidence["entries"].pop()
        with self.assertRaises(ValueError):
            self.build(evidence)

    def test_wrong_disposition_fails_closed(self):
        evidence = copy.deepcopy(self.identity)
        evidence["entries"][0]["disposition"] = "PRIMARY_REPLACEMENT"
        with self.assertRaises(ValueError):
            self.build(evidence)

    def test_evidence_cannot_target_another_batch3_row(self):
        evidence = copy.deepcopy(self.identity)
        evidence["entries"][0]["canonicalId"] = "miyorare:inventory-en:NOVELCROW"
        with self.assertRaises(ValueError):
            self.build(evidence)

    def test_safety_contract_remains_read_only(self):
        report = self.build()
        self.assertEqual(
            report["safety"],
            {
                "approvesOverlay": False,
                "mutatesAuthority": False,
                "mutatesCanonicalIds": False,
                "mutatesLastKnownGood": False,
                "mutatesRetryHeld": False,
                "promotesProvider": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
