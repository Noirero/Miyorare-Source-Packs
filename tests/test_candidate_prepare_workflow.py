import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "compatibility-farm-candidate-prepare.yml"


class CandidatePrepareWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_read_only_permissions(self):
        self.assertIn("permissions:\n  contents: read\n  actions: read", self.text)
        self.assertNotIn("contents: write", self.text)

    def test_exact_upstream_run_is_required(self):
        self.assertIn("upstream_run_id:", self.text)
        self.assertIn("run-id: ${{ inputs.upstream_run_id }}", self.text)
        self.assertIn("name: upstream-candidate-handoff", self.text)

    def test_candidate_registry_is_ephemeral_and_fail_closed(self):
        self.assertIn("tools/candidate_registry.py", self.text)
        self.assertIn("activeLastKnownGoodMutated': False", self.text)
        self.assertIn("publishEligible': False", self.text)
        self.assertIn("approvalState': 'NOT_READY'", self.text)

    def test_no_promotion_or_release_path_exists(self):
        self.assertNotIn("upstream_sync.py promote", self.text)
        self.assertNotIn("authorized_promotion.py", self.text)
        self.assertNotIn("release-source-packs.yml", self.text)
        self.assertNotIn("git push", self.text)


if __name__ == "__main__":
    unittest.main()
