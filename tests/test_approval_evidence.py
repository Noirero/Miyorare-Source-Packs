import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("approval_evidence", ROOT / "tools" / "approval_evidence.py")
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class ApprovalEvidenceTests(unittest.TestCase):
    def write_json(self, root: Path, name: str, value: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def test_binding_changes_when_repair_evidence_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            aggregate = self.write_json(
                root,
                "aggregate.json",
                {
                    "parserExecution": True,
                    "candidatePass": True,
                    "repairEvidence": {"reportedMemberships": 1},
                },
            )
            gate = self.write_json(
                root,
                "gate.json",
                {"approvalState": "WAITING_FOR_APPROVAL", "publishEligible": False},
            )
            repair = self.write_json(root, "repair-uma-source.json", {"retest": "PASS"})
            first = M.build_binding(aggregate, gate, [repair])
            repair.write_text('{"retest":"PASS","recipe":"changed"}\n', encoding="utf-8")
            second = M.build_binding(aggregate, gate, [repair])
            self.assertEqual(first["farmEvidenceSha256"], second["farmEvidenceSha256"])
            self.assertNotEqual(first["repairEvidenceSha256"], second["repairEvidenceSha256"])

    def test_binding_changes_when_aggregate_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            aggregate = self.write_json(
                root,
                "aggregate.json",
                {"parserExecution": True, "candidatePass": True, "repairEvidence": {"reportedMemberships": 0}},
            )
            gate = self.write_json(
                root,
                "gate.json",
                {"approvalState": "WAITING_FOR_APPROVAL", "publishEligible": False},
            )
            first = M.build_binding(aggregate, gate, [])
            aggregate.write_text(
                json.dumps(
                    {
                        "parserExecution": True,
                        "candidatePass": True,
                        "repairEvidence": {"reportedMemberships": 0},
                        "coverage": "changed",
                    }
                ) + "\n",
                encoding="utf-8",
            )
            second = M.build_binding(aggregate, gate, [])
            self.assertNotEqual(first["farmEvidenceSha256"], second["farmEvidenceSha256"])

    def test_repair_count_must_match_aggregate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            aggregate = self.write_json(
                root,
                "aggregate.json",
                {"parserExecution": True, "candidatePass": True, "repairEvidence": {"reportedMemberships": 2}},
            )
            gate = self.write_json(
                root,
                "gate.json",
                {"approvalState": "WAITING_FOR_APPROVAL", "publishEligible": False},
            )
            repair = self.write_json(root, "repair-one.json", {"retest": "PASS"})
            with self.assertRaisesRegex(M.ApprovalEvidenceError, "does not match"):
                M.build_binding(aggregate, gate, [repair])

    def test_non_waiting_gate_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            aggregate = self.write_json(
                root,
                "aggregate.json",
                {"parserExecution": True, "candidatePass": True, "repairEvidence": {"reportedMemberships": 0}},
            )
            gate = self.write_json(root, "gate.json", {"approvalState": "NOT_READY", "publishEligible": False})
            with self.assertRaisesRegex(M.ApprovalEvidenceError, "WAITING_FOR_APPROVAL"):
                M.build_binding(aggregate, gate, [])


if __name__ == "__main__":
    unittest.main()
