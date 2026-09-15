import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "parser_family_plan",
    ROOT / "tools" / "parser_family_plan.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ParserFamilyPlanError = MODULE.ParserFamilyPlanError
execution_plan = MODULE.execution_plan
validate_plan = MODULE.validate_plan


class ParserFamilyPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "compatibility/source-registry.json").read_text(encoding="utf-8"))
        cls.plan = json.loads((ROOT / "compatibility/parser-families.json").read_text(encoding="utf-8"))

    def test_repository_plan_is_valid(self):
        result = validate_plan(self.plan, self.registry)
        self.assertEqual("VALID", result["status"])
        self.assertGreaterEqual(result["familyCount"], 10)
        self.assertGreaterEqual(result["membershipCount"], 14)
        self.assertEqual(
            result["membershipCount"],
            sum(result["providerMembershipCounts"].values()),
        )

    def test_provider_plan_is_machine_readable_and_filtered(self):
        result = execution_plan(self.plan, self.registry, "keiyoushi")
        self.assertEqual("keiyoushi", result["provider"])
        self.assertTrue(result["include"])
        self.assertTrue(all(entry["provider"] == "keiyoushi" for entry in result["include"]))
        self.assertTrue(all(entry["testClass"].startswith("compatibilityfarm.") for entry in result["include"]))
        self.assertIn("miyorare:miyorare-id:KIRYUU", {entry["canonicalId"] for entry in result["include"]})

    def test_duplicate_provider_membership_fails_closed(self):
        broken = copy.deepcopy(self.plan)
        broken["families"].append(copy.deepcopy(broken["families"][0]))
        broken["families"][-1]["id"] = "duplicate-membership-family"
        with self.assertRaisesRegex(ParserFamilyPlanError, "duplicate parser execution membership"):
            validate_plan(broken, self.registry)

    def test_adapter_family_mismatch_fails_closed(self):
        broken = copy.deepcopy(self.plan)
        broken["families"][0]["registryAdapterFamily"] = "not-the-registry-family"
        with self.assertRaisesRegex(ParserFamilyPlanError, "registry adapter family mismatch"):
            validate_plan(broken, self.registry)

    def test_provider_must_be_real_registry_membership(self):
        broken = copy.deepcopy(self.plan)
        family = next(item for item in broken["families"] if item["provider"] == "gekkoushi")
        family["members"][0]["canonicalId"] = "miyorare:miyorare-en:WEEBCENTRAL"
        family["registryAdapterFamily"] = "custom-auth-cookie-html"
        with self.assertRaisesRegex(ParserFamilyPlanError, "is not a registry membership"):
            validate_plan(broken, self.registry)

    def test_keiyoushi_module_must_match_registry_identity(self):
        broken = copy.deepcopy(self.plan)
        family = next(item for item in broken["families"] if item["id"] == "keiyoushi-natsuid")
        family["members"][0]["module"] = "src/id/not-kiryuu"
        with self.assertRaisesRegex(ParserFamilyPlanError, "does not match registry identity"):
            validate_plan(broken, self.registry)


if __name__ == "__main__":
    unittest.main()
