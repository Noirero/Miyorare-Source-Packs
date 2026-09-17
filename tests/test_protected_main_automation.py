from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class ProtectedMainAutomationTests(unittest.TestCase):
    def test_main_upstream_sync_is_manual_read_only_recovery(self) -> None:
        sync = workflow("upstream-sync.yml")
        self.assertIn("workflow_dispatch:", sync)
        self.assertNotIn("schedule:", sync)
        self.assertIn("contents: read", sync)
        self.assertNotIn("contents: write", sync)
        self.assertNotIn("git push", sync)
        self.assertNotIn("gh pr create", sync)
        self.assertIn("Source Lab Auto Farm", sync)

    def test_auto_farm_is_the_scheduled_candidate_path(self) -> None:
        auto = workflow("source-lab-auto-farm.yml")
        self.assertIn("schedule:", auto)
        self.assertIn("compatibility-farm-foundation", auto)
        self.assertIn("source-lab-candidate-farm.yml", auto)
        self.assertIn("upstream-candidate-handoff", auto)
        self.assertIn("APPROVAL_REQUIRED", auto)
        self.assertIn("CANDIDATE_PASSED_ALL_GATES", auto)
        self.assertIn("HELD", auto)
        self.assertIn("INFRASTRUCTURE_FAILURE", auto)
        self.assertIn("NO_UPSTREAM_CHANGE", auto)
        self.assertIn("lastKnownGood", auto)
        self.assertNotIn("gh pr create", auto)
        self.assertNotIn("gh pr merge", auto)

    def test_auto_farm_isolates_provider_candidates_and_suppresses_exact_held_sha(self) -> None:
        auto = workflow("source-lab-auto-farm.yml")
        self.assertIn("selected_provider", auto)
        self.assertIn("source_lab_scope_plan.py", auto)
        self.assertIn("upstream_sync_impl.py", auto)
        self.assertIn("shutil.copy2(original, impl)", auto)
        self.assertIn("if not args or args[0] != 'plan'", auto)
        self.assertIn("exception.get('candidate') == item['candidate']", auto)
        self.assertIn("ALL_OUTSTANDING_CANDIDATES_HELD", auto)
        self.assertIn("lastAttemptProvider", auto)
        self.assertIn("exceptions", auto)
        self.assertIn("recordedAt", auto)

    def test_auto_farm_scoping_does_not_patch_authoritative_workflow_text(self) -> None:
        auto = workflow("source-lab-auto-farm.yml")
        self.assertNotIn("needle = r'''", auto)
        self.assertNotIn("replacement = r'''", auto)
        self.assertNotIn("workflow.write_text", auto)
        self.assertNotIn("SOURCE_LAB_PROVIDER_SCOPE", auto)
        self.assertIn("authoritative upstream sync helper is missing", auto)
        self.assertIn("selected provider no longer differs from LKG", auto)
        self.assertIn("git -C intake-branch add tools/upstream_sync.py tools/upstream_sync_impl.py tools/source_lab_scope_plan.py", auto)

    def test_auto_farm_distinguishes_infrastructure_from_held_candidate_failures(self) -> None:
        auto = workflow("source-lab-auto-farm.yml")
        self.assertIn("UPSTREAM_INTAKE_INFRASTRUCTURE_FAILURE", auto)
        self.assertIn("UPSTREAM_INTAKE_NOT_SAFE", auto)
        self.assertIn("CANDIDATE_FARM_INFRASTRUCTURE_FAILURE", auto)
        self.assertIn("CANDIDATE_FARM_GATE_FAILED", auto)
        self.assertIn("Set up ", auto)
        self.assertIn("Classify Candidate Farm failure", auto)

    def test_sync_result_is_read_only_and_never_opens_automation_pr(self) -> None:
        status = workflow("upstream-sync-status.yml")
        self.assertIn("actions: read", status)
        self.assertIn("contents: read", status)
        self.assertNotIn("contents: write", status)
        self.assertNotIn("pull-requests: write", status)
        self.assertNotIn("git push", status)
        self.assertNotIn("gh pr create", status)
        self.assertNotIn("AUTOMATION_BRANCH", status)
        self.assertIn("Routine upstream intake no longer opens or refreshes automation pull requests", status)

    def test_manual_source_lab_run_farm_remains_recovery_only(self) -> None:
        run_farm = workflow("source-lab-run-farm.yml")
        self.assertIn("workflow_dispatch:", run_farm)
        self.assertIn("EXPECTED_OWNER_ID: '149634319'", run_farm)
        self.assertIn("compatibility-farm-foundation", run_farm)
        self.assertIn("source-lab-candidate-farm.yml", run_farm)

    def test_candidate_farm_stages_waiting_for_approval_only_after_real_parser_gate(self) -> None:
        farm = workflow("source-lab-candidate-farm.yml")
        self.assertIn("Enforce all parser jobs before staging", farm)
        self.assertIn("candidate_gate.py", farm)
        self.assertIn("approval_evidence.py", farm)
        self.assertIn("WAITING_FOR_APPROVAL", farm)
        self.assertIn("activeLastKnownGoodMutated", farm)
        self.assertIn("publishEligible", farm)

    def test_release_after_merge_remains_legacy_only(self) -> None:
        release = workflow("release-source-packs-after-merge.yml")
        self.assertIn("branches:\n      - main", release)
        self.assertIn("gh workflow run release-source-packs.yml", release)

    def test_android_sdk_guard_is_read_only_audit(self) -> None:
        audit = workflow("repair-android-sdk-setup.yml")
        self.assertIn("name: Audit Android SDK Setup", audit)
        self.assertIn("contents: read", audit)
        self.assertNotIn("contents: write", audit)
        self.assertNotIn("pull-requests: write", audit)
        self.assertNotIn("git push", audit)
        self.assertNotIn("gh pr create", audit)
        self.assertIn("pull_request:", audit)
        self.assertIn("'.github/workflows/**'", audit)
        self.assertIn("packages: platform-tools", audit)


if __name__ == "__main__":
    unittest.main()
