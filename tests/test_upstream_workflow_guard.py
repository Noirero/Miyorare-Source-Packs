import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "upstream-sync.yml"


class UpstreamWorkflowGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_permissions_are_read_only(self):
        self.assertIn("permissions:\n  contents: read\n  actions: read", self.text)
        self.assertNotIn("contents: write", self.text)

    def test_direct_promotion_is_absent(self):
        self.assertNotIn("Promote passing candidates", self.text)
        self.assertNotIn("tools/upstream_sync.py promote ", self.text)
        self.assertNotIn("git push origin", self.text)

    def test_release_dispatch_is_absent(self):
        self.assertNotIn("release-source-packs.yml", self.text)
        self.assertNotIn("gh workflow run", self.text)

    def test_candidate_handoff_is_fail_closed(self):
        self.assertIn("candidate-handoff:", self.text)
        self.assertIn("approvalState': 'NOT_READY'", self.text)
        self.assertIn("nextAction': 'RUN_REAL_PARSER_COMPATIBILITY_FARM'", self.text)
        self.assertIn("registryMutationAllowed': False", self.text)
        self.assertIn("releaseDispatchAllowed': False", self.text)
        self.assertIn("publishEligible': False", self.text)


if __name__ == "__main__":
    unittest.main()
