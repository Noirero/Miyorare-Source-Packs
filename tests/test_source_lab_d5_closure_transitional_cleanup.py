from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "d5", ROOT / "tools" / "source_lab_d5_closure_transitional_cleanup.py"
)
assert SPEC and SPEC.loader
D5 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D5)


class D5ClosureTests(unittest.TestCase):
    def baseline(self) -> dict:
        return {
            "schemaVersion": 1,
            "phase": "TRACK_D_D5_CLOSURE_TRANSITIONAL_CLEANUP",
            "sourcePacksAfterD4": "a" * 40,
            "d4Artifact": {"requiredStatus": "D4_LONG_TERM_AUTOMATION_ACCEPTANCE_PROVEN"},
            "permanentMaintenanceWorkflows": [
                ".github/workflows/permanent-a.yml",
                ".github/workflows/permanent-b.yml",
            ],
            "scheduledCoverage": {
                "inventory": ".github/workflows/permanent-a.yml",
            },
            "retiredTransitionalWorkflows": [
                ".github/workflows/old-stage.yml",
            ],
            "frozenEvidence": ["compatibility/evidence/old.json"],
            "historicalImplementations": ["tools/old.py", "tests/test_old.py"],
            "closureSemantics": {
                "trackDClosedMeans": "permanent model established",
                "doesNotMean": "all sources healthy",
                "unresolvedOperationalHandoffsMayRemain": True,
            },
        }

    def d4(self, handoffs: list[str] | None = None) -> dict:
        ids = handoffs if handoffs is not None else ["source:a", "source:b"]
        return {
            "phase": "TRACK_D_D4_LONG_TERM_AUTOMATION_ACCEPTANCE",
            "status": "D4_LONG_TERM_AUTOMATION_ACCEPTANCE_PROVEN",
            "trackDClosed": False,
            "nextStage": "TRACK_D_D5_CLOSURE_TRANSITIONAL_CLEANUP",
            "proofs": {
                "workflowChain": {"status": "PROVEN"},
                "lastKnownGoodRollbackSafety": {"status": "PROVEN"},
                "packAndReleaseAcceptance": {"status": "PROVEN"},
            },
            "safety": {
                "mutateFarmLifecycle": False,
                "publishRelease": False,
            },
            "operationalHandoffs": {
                "carriedForwardFromD3": True,
                "count": len(ids),
                "ownerPackAuthorityRequired": ids,
            },
        }

    def root(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        files = {
            ".github/workflows/permanent-a.yml": "on:\n  schedule:\n    - cron: '0 0 * * *'\n",
            ".github/workflows/permanent-b.yml": "on:\n  workflow_dispatch:\n",
            "compatibility/evidence/old.json": "{}\n",
            "tools/old.py": "pass\n",
            "tests/test_old.py": "pass\n",
        }
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return temp, root

    def build(self, baseline: dict | None = None, d4: dict | None = None, root: Path | None = None) -> dict:
        return D5.build_report(
            baseline or self.baseline(),
            d4 or self.d4(),
            root or Path("."),
            control_head="b" * 40,
            source_packs_base="a" * 40,
            farm_commit="c" * 40,
            miyorare_amain2="d" * 40,
        )

    def test_handoffs_do_not_block_track_closure(self):
        temp, root = self.root()
        self.addCleanup(temp.cleanup)
        report = self.build(root=root)
        self.assertTrue(report["trackDClosed"])
        self.assertEqual(report["status"], "TRACK_D_CLOSED_WITH_OPERATIONAL_HANDOFFS")
        self.assertEqual(report["operationalHandoffs"]["count"], 2)
        self.assertFalse(report["operationalHandoffs"]["blocksTrackClosure"])
        self.assertIsNone(report["nextStage"])

    def test_zero_handoffs_closes_clean(self):
        temp, root = self.root()
        self.addCleanup(temp.cleanup)
        report = self.build(d4=self.d4([]), root=root)
        self.assertEqual(report["status"], "TRACK_D_CLOSED")

    def test_missing_permanent_workflow_fails_closed(self):
        temp, root = self.root()
        self.addCleanup(temp.cleanup)
        (root / ".github/workflows/permanent-b.yml").unlink()
        with self.assertRaises(D5.ClosureError):
            self.build(root=root)

    def test_scheduled_coverage_must_remain_scheduled(self):
        temp, root = self.root()
        self.addCleanup(temp.cleanup)
        (root / ".github/workflows/permanent-a.yml").write_text("on:\n  workflow_dispatch:\n", encoding="utf-8")
        with self.assertRaises(D5.ClosureError):
            self.build(root=root)

    def test_transitional_workflow_must_be_retired(self):
        temp, root = self.root()
        self.addCleanup(temp.cleanup)
        path = root / ".github/workflows/old-stage.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("on: workflow_dispatch\n", encoding="utf-8")
        with self.assertRaises(D5.ClosureError):
            self.build(root=root)

    def test_frozen_evidence_must_be_preserved(self):
        temp, root = self.root()
        self.addCleanup(temp.cleanup)
        (root / "compatibility/evidence/old.json").unlink()
        with self.assertRaises(D5.ClosureError):
            self.build(root=root)

    def test_d4_must_be_fully_proven(self):
        temp, root = self.root()
        self.addCleanup(temp.cleanup)
        d4 = self.d4()
        d4["proofs"]["workflowChain"]["status"] = "FAILED"
        with self.assertRaises(D5.ClosureError):
            self.build(d4=d4, root=root)

    def test_d4_safety_violation_fails_closed(self):
        temp, root = self.root()
        self.addCleanup(temp.cleanup)
        d4 = self.d4()
        d4["safety"]["publishRelease"] = True
        with self.assertRaises(D5.ClosureError):
            self.build(d4=d4, root=root)

    def test_handoff_count_must_match_list(self):
        temp, root = self.root()
        self.addCleanup(temp.cleanup)
        d4 = self.d4()
        d4["operationalHandoffs"]["count"] = 99
        with self.assertRaises(D5.ClosureError):
            self.build(d4=d4, root=root)


if __name__ == "__main__":
    unittest.main()
