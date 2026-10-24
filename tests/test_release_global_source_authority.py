from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "release-source-packs.yml").read_text(encoding="utf-8")


class ReleaseGlobalSourceAuthorityTests(unittest.TestCase):
    def test_global_release_verification_uses_pinned_manifest_authority(self) -> None:
        self.assertIn("manifest['packs']['global'].get('gekkoushiSources')", WORKFLOW)
        self.assertIn("expected_sources = set(expected_list)", WORKFLOW)
        self.assertNotIn("{'EXHENTAI', 'GELBOORU', 'RAWDEX', 'NEWXTOON'}", WORKFLOW)

    def test_release_notes_do_not_claim_beta_lineage_for_pinned_builder(self) -> None:
        self.assertNotIn("(beta lineage)", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
