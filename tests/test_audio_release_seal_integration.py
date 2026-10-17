import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEAL_WORKFLOW = ROOT / ".github" / "workflows" / "source-pack-release-seal.yml"


class AudioReleaseSealIntegrationTests(unittest.TestCase):
    def test_p3_audio_is_staged_before_release_lock_is_built(self) -> None:
        text = SEAL_WORKFLOW.read_text(encoding="utf-8")
        stage = text.index("Validate and stage exact P3 audio catalog before sealing")
        download = text.index("Download staged payload")
        lock = text.index("Build canonical release lock while draft")
        self.assertLess(stage, download)
        self.assertLess(download, lock)

    def test_release_path_requires_p3_eligibility_and_exact_runtime_contract(self) -> None:
        text = SEAL_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--require-release-eligible", text)
        self.assertIn("validate_audio_runtime_contract.py", text)
        self.assertIn("miyorare-audio-extensions.json", text)

    def test_existing_immutable_seal_is_not_retroactively_mutated(self) -> None:
        text = SEAL_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("PREEXISTING_SEAL", text)
        self.assertNotIn("--clobber", text)


if __name__ == "__main__":
    unittest.main()
