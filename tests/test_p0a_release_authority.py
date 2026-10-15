from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class P0AReleaseAuthorityTests(unittest.TestCase):
    def test_after_merge_only_wakes_authoritative_controller(self) -> None:
        after_merge = workflow("release-source-packs-after-merge.yml")
        self.assertIn("gh workflow run source-pack-autonomous-release.yml", after_merge)
        self.assertNotIn("gh workflow run release-source-packs.yml", after_merge)
        self.assertNotIn("Determine next immutable source-pack version", after_merge)

    def test_contract_keeps_one_official_publisher(self) -> None:
        contract = (ROOT / "compatibility" / "miyorare-source-pack-contract.v1.json").read_text(encoding="utf-8")
        self.assertIn('"releaseWorkflow": ".github/workflows/release-source-packs.yml"', contract)

    def test_source_lab_exact_commit_security_is_not_silently_weakened(self) -> None:
        source_lab = workflow("source-lab-publish-candidate.yml")
        required = (
            "gh attestation verify",
            "foundationCommit",
            "evidenceBinding",
            "source-lab-publish-${GITHUB_RUN_ID}",
            "FOUNDATION_COMMIT",
            "source-lab-publish-receipt.json",
        )
        for marker in required:
            self.assertIn(marker, source_lab)

    def test_source_lab_direct_publish_is_explicit_remaining_p0a_debt(self) -> None:
        source_lab = workflow("source-lab-publish-candidate.yml")
        self.assertIn("gh workflow run release-source-packs.yml", source_lab)
        guardrail = (ROOT / "docs" / "governance" / "P0A_STABLE_RELEASE_AUTHORITY.md").read_text(encoding="utf-8")
        self.assertIn("remaining P0-A debt", guardrail)
        self.assertIn("exact signed Foundation commit", guardrail)


if __name__ == "__main__":
    unittest.main()
