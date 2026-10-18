from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class SignedReleaseCurrentWorkflowTests(unittest.TestCase):
    def test_release_workflow_accepts_exact_signed_farm_and_control_snapshots(self) -> None:
        release = workflow("release-source-packs.yml")
        self.assertIn("foundation_commit:", release)
        self.assertIn("control_commit:", release)
        self.assertIn("FOUNDATION_COMMIT_OVERRIDE: ${{ inputs.foundation_commit }}", release)
        self.assertIn("CONTROL_COMMIT_OVERRIDE: ${{ inputs.control_commit }}", release)
        self.assertIn("ref: ${{ inputs.foundation_commit || 'compatibility-farm-foundation' }}", release)
        self.assertIn("Checked-out Compatibility Farm does not match signed Foundation override.", release)
        self.assertIn("Dispatched release workflow does not match the signed controller control-plane commit.", release)

    def test_signed_controller_uses_current_workflow_with_signed_farm_state(self) -> None:
        controller = workflow("source-pack-autonomous-release.yml")
        signed = controller.split("\n  signed_source_lab_release:\n", 1)[1]
        self.assertIn("--ref main -f version=\"$VERSION\" -f foundation_commit=\"$FOUNDATION_COMMIT\" -f control_commit=\"$GITHUB_SHA\"", signed)
        self.assertIn("--branch main", signed)
        self.assertIn('select(.headSha == \\"$GITHUB_SHA\\")', signed)
        self.assertIn('[[ "$main_sha" == "$GITHUB_SHA" ]]', signed)
        self.assertNotIn('--ref "$RELEASE_REF" -f version="$VERSION"', signed)
        self.assertNotIn('--branch "$RELEASE_REF"', signed)
        self.assertNotIn('select(.headSha == \\"$FOUNDATION_COMMIT\\")', signed)


if __name__ == "__main__":
    unittest.main()
