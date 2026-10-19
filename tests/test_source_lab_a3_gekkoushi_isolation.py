from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "source-lab-a3-gekkoushi-isolation-canary.yml"


class SourceLabA3GekkoushiIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_canary_is_owner_only_read_only_and_exact_sha_bound(self) -> None:
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("EXPECTED_OWNER_ID: '149634319'", self.text)
        self.assertIn("contents: read", self.text)
        self.assertNotIn("contents: write", self.text)
        self.assertIn("FOUNDATION_SHA", self.text)
        self.assertIn("CANDIDATE_SHA", self.text)
        self.assertIn("compatibility-farm-foundation", self.text)
        self.assertNotIn("git push", self.text)
        self.assertNotIn("gh pr", self.text)

    def test_gekkoushi_memberships_run_as_non_fail_fast_matrix(self) -> None:
        self.assertIn("plan --provider gekkoushi", self.text)
        self.assertIn("fail-fast: false", self.text)
        self.assertIn("max-parallel: 6", self.text)
        self.assertIn("matrix: ${{ fromJson(needs.prepare.outputs.matrix) }}", self.text)
        self.assertIn("--tests \"$TEST_CLASS\"", self.text)
        self.assertNotIn("--tests compatibilityfarm.DoujinDesuParserHarnessTest", self.text)
        self.assertNotIn("--tests compatibilityfarm.ShinigamiGekkoushiParserHarnessTest", self.text)

    def test_only_selected_harness_and_repairs_are_installed(self) -> None:
        self.assertIn('harness="${TEST_CLASS##*.}.kt"', self.text)
        self.assertIn('cp "farm/compatibility/harness/gekkoushi/$harness"', self.text)
        self.assertIn("Apply only selected membership repair recipes", self.text)
        self.assertIn("Unsupported repair-bearing Gekkoushi membership", self.text)
        self.assertIn("miyorare:miyorare-id:SHINIGAMI", self.text)
        self.assertIn("miyorare:miyorare-en:BATCAVE", self.text)

    def test_parser_failure_is_evidence_but_infrastructure_failure_is_not_hidden(self) -> None:
        self.assertIn("case \"$rc\" in", self.text)
        self.assertIn("0|2) ;;", self.text)
        self.assertIn("Could not normalize isolated parser evidence", self.text)
        self.assertIn("isolated report must contain exactly one membership", self.text)
        self.assertIn("PASS evidence cannot come from a failed parser step", self.text)
        self.assertIn("FAIL evidence unexpectedly came from a successful parser step", self.text)

    def test_aggregate_requires_complete_evidence_without_promotion(self) -> None:
        self.assertIn("Require one normalized receipt per ACTIVE membership", self.text)
        self.assertIn("Isolation evidence incomplete", self.text)
        self.assertIn("allMembershipsExecuted", self.text)
        self.assertIn("parserFailuresCancelUnrelatedSources", self.text)
        self.assertIn("promotionAttempted", self.text)
        self.assertNotIn("source-lab-promote-candidate", self.text)
        self.assertNotIn("candidate_lifecycle.py", self.text)


if __name__ == "__main__":
    unittest.main()
