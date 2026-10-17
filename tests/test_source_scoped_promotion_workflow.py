import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/source-lab-promote-candidate.yml"
OLD = "a" * 40
NEW = "b" * 40
SOURCES = ["BACAMI", "KIRYUU", "KOMIKU", "ASURASCANS", "AQUAMANGA", "BATCAVE"]
SAFE = SOURCES[:-1]


def promotion_program() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    marker = "      - name: Advance Compatibility Farm baseline and scoped runtime status"
    section = text.split(marker, 1)[1].split("      - name: Reconcile explicit provider release eligibility", 1)[0]
    program = section.split("          python3 - <<'PY'\n", 1)[1].rsplit("\n          PY", 1)[0]
    return textwrap.dedent(program)


def source(name: str) -> dict:
    return {
        "canonicalId": name,
        "providers": ["keiyoushi"],
        "currentVersion": {"keiyoushi": OLD},
        "lastKnownGood": {"keiyoushi": OLD},
        "healthyHistory": [OLD],
        "updateState": "HELD" if name == "BATCAVE" else "CANDIDATE",
        "approvalState": "NOT_READY",
        "ownerActionRequired": False,
        "publishEligible": False,
    }


class ScopedPromotionWorkflowTests(unittest.TestCase):
    def run_program(self, scope):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "farm/compatibility").mkdir(parents=True)
        (root / "farm/upstream").mkdir(parents=True)
        (root / "build").mkdir()
        pending = {
            "candidateSetId": "c" * 64,
            "providers": {"keiyoushi": {"current": OLD, "candidate": NEW}},
            "evidenceBinding": {"schemaVersion": 1},
            "sourceScope": {"keiyoushi": scope},
        }
        approval = {"approvedBy": "Noirero"}
        registry = {"providerBaselines": {"keiyoushi": OLD}, "sources": [source(name) for name in SOURCES]}
        status = {
            "schema": 3,
            "approvalCandidate": pending,
            "providers": {
                "keiyoushi": {
                    "activeCommit": OLD,
                    "lastKnownGood": OLD,
                    "healthyHistory": [OLD],
                    "candidate": {"commit": NEW},
                }
            },
        }
        for path, value in (
            (root / "build/pending-approval.json", pending),
            (root / "build/approval-proof.json", approval),
            (root / "farm/compatibility/source-registry.json", registry),
            (root / "farm/upstream/status.json", status),
        ):
            path.write_text(json.dumps(value), encoding="utf-8")
        env = os.environ.copy()
        env.update(GITHUB_RUN_ID="77", APPROVAL_RUN_ID="66")
        result = subprocess.run(["python3", "-c", promotion_program()], cwd=root, env=env, text=True, capture_output=True)
        return temp, root, result

    def test_five_sources_promote_while_batcave_remains_on_lkg(self):
        temp, root, result = self.run_program(SAFE)
        try:
            self.assertEqual(0, result.returncode, result.stderr)
            registry = json.loads((root / "farm/compatibility/source-registry.json").read_text())
            by_id = {item["canonicalId"]: item for item in registry["sources"]}
            self.assertEqual(NEW, registry["providerBaselines"]["keiyoushi"])
            for name in SAFE:
                self.assertEqual(NEW, by_id[name]["currentVersion"]["keiyoushi"])
                self.assertEqual(NEW, by_id[name]["lastKnownGood"]["keiyoushi"])
                self.assertEqual("PROMOTED", by_id[name]["updateState"])
            self.assertEqual(OLD, by_id["BATCAVE"]["currentVersion"]["keiyoushi"])
            self.assertEqual(OLD, by_id["BATCAVE"]["lastKnownGood"]["keiyoushi"])
            self.assertEqual("HELD", by_id["BATCAVE"]["updateState"])
            status = json.loads((root / "farm/upstream/status.json").read_text())
            self.assertEqual(NEW, status["providers"]["keiyoushi"]["activeCommit"])
            self.assertEqual(SAFE, status["lastPromotion"]["sourceScope"]["keiyoushi"])
        finally:
            temp.cleanup()

    def test_unknown_scoped_source_fails_closed_without_state_write(self):
        temp, root, result = self.run_program(SAFE + ["NOT_A_MEMBER"])
        try:
            self.assertNotEqual(0, result.returncode)
            registry = json.loads((root / "farm/compatibility/source-registry.json").read_text())
            self.assertEqual(OLD, registry["providerBaselines"]["keiyoushi"])
            self.assertTrue(all(item["lastKnownGood"]["keiyoushi"] == OLD for item in registry["sources"]))
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
