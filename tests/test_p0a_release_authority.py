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

    def test_source_lab_routes_signed_request_through_authoritative_controller(self) -> None:
        source_lab = workflow("source-lab-publish-candidate.yml")
        controller = workflow("source-pack-autonomous-release.yml")
        self.assertIn("gh workflow run source-pack-autonomous-release.yml", source_lab)
        self.assertNotIn("gh workflow run release-source-packs.yml", source_lab)
        self.assertNotIn("Resolve next immutable Source Pack version", source_lab)
        self.assertIn("release_mode=source_lab_signed", source_lab)
        self.assertIn("source-pack-signed-release-${{ inputs.candidate_set_id }}", source_lab)
        self.assertIn("source_lab_signed", controller)
        self.assertIn("Dispatch sole Source Pack publisher on exact signed ref", controller)

    def test_source_lab_exact_commit_security_is_preserved_end_to_end(self) -> None:
        source_lab = workflow("source-lab-publish-candidate.yml")
        controller = workflow("source-pack-autonomous-release.yml")
        source_lab_required = (
            "gh attestation verify",
            "foundationCommit",
            "evidenceBinding",
            "source-lab-publish-${GITHUB_RUN_ID}",
            "FOUNDATION_COMMIT",
            "source-lab-publish-receipt.json",
        )
        for marker in source_lab_required:
            self.assertIn(marker, source_lab)
        controller_required = (
            "gh attestation verify build/source-lab-signing-manifest.json",
            "requested Foundation commit differs from signed receipt",
            "temporary release ref no longer points to the exact signed Foundation commit",
            '--ref "$RELEASE_REF"',
            'select(.headSha == \\"$FOUNDATION_COMMIT\\")',
        )
        for marker in controller_required:
            self.assertIn(marker, controller)

    def test_stable_version_allocation_is_not_duplicated_in_source_lab(self) -> None:
        source_lab = workflow("source-lab-publish-candidate.yml")
        controller = workflow("source-pack-autonomous-release.yml")
        self.assertNotIn("miyorare-sources-v(\\d+)", source_lab)
        self.assertNotIn("Resolve next immutable Source Pack version", source_lab)
        self.assertIn("Allocate next immutable stable version", controller)


if __name__ == "__main__":
    unittest.main()
