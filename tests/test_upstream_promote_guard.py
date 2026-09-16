import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "upstream_sync.py"


class UpstreamPromoteGuardTests(unittest.TestCase):
    def test_legacy_promote_cli_requires_authorization_and_receipt(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "promote",
                "--registry",
                "does-not-matter.json",
                "--provider",
                "uma",
                "--commit",
                "a" * 40,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("--authorization", completed.stderr)
        self.assertIn("--receipt", completed.stderr)


if __name__ == "__main__":
    unittest.main()
