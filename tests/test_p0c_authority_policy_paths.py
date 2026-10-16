from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class P0CAuthorityPolicyPathTests(unittest.TestCase):
    def test_authority_artifacts_exist_at_canonical_paths(self) -> None:
        for path in (
            "governance/automation-promotion-authority.v1.json",
            "tools/validate_promotion_authority.py",
            "docs/governance/P0C_AUTOMATION_PROMOTION_AUTHORITY.md",
        ):
            self.assertTrue((ROOT / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
