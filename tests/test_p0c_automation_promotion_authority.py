from pathlib import Path
import json
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class P0CAutomationPromotionAuthorityTests(unittest.TestCase):
    def test_machine_authority_contract_is_fail_closed(self) -> None:
        policy = json.loads((ROOT / "governance/automation-promotion-authority.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["schemaVersion"], 1)
        self.assertEqual(policy["defaultDecision"], "HELD")
        self.assertFalse(policy["classes"]["provider_baseline"]["automationMayMerge"])
        self.assertTrue(policy["classes"]["provider_baseline"]["ownerApprovalRequired"])
        self.assertFalse(policy["classes"]["source_onboarding"]["automationMayMerge"])
        self.assertTrue(policy["classes"]["source_onboarding"]["ownerApprovalRequired"])
        self.assertTrue(policy["classes"]["builder_baseline"]["automationMayMerge"])
        self.assertIn("main-required-gates", policy["classes"]["builder_baseline"]["requiredGates"])

    def test_provider_auto_promote_flag_is_not_authority(self) -> None:
        registry = json.loads((ROOT / "upstream/registry.json").read_text(encoding="utf-8"))
        self.assertTrue(any(item.get("autoPromote") is True for item in registry["providers"].values()))
        policy = json.loads((ROOT / "governance/automation-promotion-authority.v1.json").read_text(encoding="utf-8"))
        self.assertTrue(policy["classes"]["provider_baseline"]["ownerApprovalRequired"])
        self.assertFalse(policy["classes"]["provider_baseline"]["automationMayMerge"])

    def test_authority_validator_passes_repository_state(self) -> None:
        subprocess.run([sys.executable, str(ROOT / "tools/validate_promotion_authority.py")], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
