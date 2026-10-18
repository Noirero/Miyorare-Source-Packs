from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class P0ASignedRequestBindingTests(unittest.TestCase):
    def test_controller_requires_authorized_request_provenance(self) -> None:
        controller = workflow("source-pack-autonomous-release.yml")
        self.assertIn("EXPECTED_OWNER_ID: '149634319'", controller)
        self.assertIn("EXPECTED_AUTOMATION_ID: '41898282'", controller)
        self.assertIn('[[ "$GITHUB_ACTOR_ID" == "$EXPECTED_OWNER_ID" || "$GITHUB_ACTOR_ID" == "$EXPECTED_AUTOMATION_ID" ]]', controller)
        self.assertIn("Verify authorized Source Lab request run", controller)
        self.assertIn('"path": ".github/workflows/source-lab-publish-candidate.yml"', controller)
        self.assertIn("Source Lab request run actor is not the authorized owner", controller)

    def test_source_lab_controller_run_is_correlated_by_unique_request_id(self) -> None:
        source_lab = workflow("source-lab-publish-candidate.yml")
        controller = workflow("source-pack-autonomous-release.yml")
        self.assertIn('request_id="source-lab-${GITHUB_RUN_ID}-${CANDIDATE_SET_ID}"', source_lab)
        self.assertIn('-f request_id="$request_id"', source_lab)
        self.assertIn('-f request_run_id="$GITHUB_RUN_ID"', source_lab)
        self.assertIn('select(.displayTitle == \\"$expected_title\\")', source_lab)
        self.assertNotIn("started_epoch", source_lab)
        self.assertIn("run-name: Source Pack control ${{ inputs.request_id || github.run_id }}", controller)
        self.assertIn('[[ "$REQUEST_ID" == "source-lab-${REQUEST_RUN_ID}-${CANDIDATE_SET_ID}" ]]', controller)

    def test_signed_release_reaps_stale_queued_publishers_but_keeps_fresh_runs_fail_closed(self) -> None:
        controller = workflow("source-pack-autonomous-release.yml")
        signed = controller.split("\n  signed_source_lab_release:\n", 1)[1]
        self.assertIn("Clean stale queued releases and refuse duplicate active publisher", signed)
        self.assertIn('stale_before="$((now_epoch - 21600))"', signed)
        self.assertIn('gh run cancel "$run_id"', signed)
        self.assertIn("status,databaseId,createdAt", signed)
        self.assertIn('.status == \\"in_progress\\" or (.status == \\"queued\\"', signed)
        self.assertIn("A fresh Source Pack publisher run is already queued/running.", signed)
        self.assertNotIn("select(.status == \"queued\" or .status == \"in_progress\")", signed)


if __name__ == "__main__":
    unittest.main()