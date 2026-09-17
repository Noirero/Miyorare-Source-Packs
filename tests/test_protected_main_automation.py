from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class ProtectedMainAutomationTests(unittest.TestCase):
    def test_upstream_sync_hands_off_registry_without_pushing_refs(self) -> None:
        sync = workflow("upstream-sync.yml")
        self.assertNotIn("git push", sync)
        self.assertIn("actions/upload-artifact@v4", sync)
        self.assertIn("name: promoted-upstream-registry", sync)
        self.assertIn("path: upstream/registry.json", sync)

    def test_sync_result_writes_only_automation_branch_and_uses_pr(self) -> None:
        status = workflow("upstream-sync-status.yml")
        self.assertIn(
            "AUTOMATION_BRANCH: automation/upstream-sync-${{ github.event.workflow_run.head_branch }}",
            status,
        )
        self.assertIn('origin "HEAD:${AUTOMATION_BRANCH}"', status)
        self.assertNotIn('origin "HEAD:${HEAD_BRANCH}"', status)
        self.assertIn("gh pr create", status)
        self.assertIn("gh workflow run upstream-sync-pr-check.yml", status)
        self.assertIn("gh workflow run source-pack-contract.yml", status)
        self.assertIn("promoted-upstream-registry", status)

    def test_automation_pr_validation_supports_explicit_dispatch(self) -> None:
        check = workflow("upstream-sync-pr-check.yml")
        self.assertIn("workflow_dispatch:", check)
        self.assertIn("github.event.pull_request.number || github.ref_name", check)

    def test_release_is_dispatched_only_from_merged_atomic_state(self) -> None:
        release = workflow("release-source-packs-after-merge.yml")
        self.assertIn("branches:\n      - main", release)
        self.assertIn("- upstream/registry.json", release)
        self.assertIn("status.get('schema') != 2", release)
        self.assertIn("status.get('workflowRunId') != outcome.get('workflowRunId')", release)
        self.assertIn("status_lkg != registry_lkg", release)
        self.assertIn("outcome.get('outcome') not in {'PASS', 'HELD'}", release)
        self.assertIn("outcome.get('activeSetSafe') is not True", release)
        self.assertIn("gh workflow run release-source-packs.yml", release)
        self.assertIn("--ref main", release)

    def test_android_sdk_repair_uses_pr_instead_of_main_push(self) -> None:
        repair = workflow("repair-android-sdk-setup.yml")
        self.assertNotIn("git push origin HEAD:main", repair)
        self.assertIn('git push origin "HEAD:${REPAIR_BRANCH}"', repair)
        self.assertIn("gh pr create", repair)
        self.assertIn("--base main", repair)


if __name__ == "__main__":
    unittest.main()
