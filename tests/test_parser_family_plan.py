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

    def required_sources(self, registry=None):
        registry = registry or self.registry
        return [
            source for source in registry["sources"]
            if source.get("compatibilityEnrollment", {}).get("parserCoverageRequired", True)
        ]

    def test_repository_plan_is_valid_and_covers_active_memberships(self):
        result = validate_plan(self.plan, self.registry)
        required_sources = self.required_sources()
        required_memberships = sum(len(source["providers"]) for source in required_sources)
        provider_counts = {
            provider: sum(provider in source["providers"] for source in required_sources)
            for provider in self.registry["scope"]["providers"]
        }

        self.assertEqual("VALID", result["status"])
        self.assertEqual(required_memberships, result["membershipCount"])
        self.assertEqual(required_memberships, result["requiredMembershipCount"])
        self.assertEqual(len(required_sources), result["requiredSourceCount"])
        self.assertEqual(len(self.registry["sources"]) - len(required_sources), result["pendingSourceCount"])
        self.assertEqual(provider_counts, result["providerMembershipCounts"])
        self.assertEqual(0, result["pendingDeclaredMembershipCount"])

    def test_aarlas_is_pending_and_not_in_release_execution_plan(self):
        aarlas = next(
            source for source in self.registry["sources"]
            if source["canonicalId"] == "miyorare:inventory-id:AARLAS"
        )
        self.assertEqual(
            {"state": "PENDING", "parserCoverageRequired": False},
            aarlas["compatibilityEnrollment"],
        )
        result = execution_plan(self.plan, self.registry)
        canonical_ids = {entry["canonicalId"] for entry in result["include"]}
        self.assertNotIn("miyorare:inventory-id:AARLAS", canonical_ids)

    def test_provider_plan_is_machine_readable_and_filtered(self):
        result = execution_plan(self.plan, self.registry, "keiyoushi")
        required_sources = self.required_sources()
        expected_keiyoushi = sum("keiyoushi" in source["providers"] for source in required_sources)
        self.assertEqual("keiyoushi", result["provider"])
        self.assertEqual(expected_keiyoushi, result["membershipCount"])
        self.assertEqual(len(required_sources), result["requiredSourceCount"])
        self.assertEqual(len(self.registry["sources"]) - len(required_sources), result["pendingSourceCount"])
        self.assertTrue(all(entry["provider"] == "keiyoushi" for entry in result["include"]))
        self.assertTrue(all(entry["testClass"].startswith("compatibilityfarm.") for entry in result["include"]))
        self.assertIn("miyorare:miyorare-id:KIRYUU", {entry["canonicalId"] for entry in result["include"]})
        self.assertTrue(all(entry["runtimeProfile"] for entry in result["include"]))

    def test_activating_source_without_parser_family_fails_preflight(self):
        broken = copy.deepcopy(self.registry)
        aarlas = next(
            source for source in broken["sources"]
            if source["canonicalId"] == "miyorare:inventory-id:AARLAS"
        )
        aarlas["compatibilityEnrollment"] = {
            "state": "ACTIVE",
            "parserCoverageRequired": True,
        }
        with self.assertRaisesRegex(
            ParserFamilyPlanError,
            "ACTIVE registry membership.*missing real parser family coverage",
        ):
            validate_plan(self.plan, broken)

    def test_pending_source_can_be_profiled_without_entering_release_plan(self):
        registry = copy.deepcopy(self.registry)
        plan = copy.deepcopy(self.plan)
        aarlas = next(
            source for source in registry["sources"]
            if source["canonicalId"] == "miyorare:inventory-id:AARLAS"
        )
        aarlas["adapterFamily"] = "zeistmanga"
        aarlas["authType"] = "NO_AUTH"
        plan["families"].append(
            {
                "id": "keiyoushi-zeistmanga-pending",
                "provider": "keiyoushi",
                "registryAdapterFamily": "zeistmanga",
                "providerParserFamily": "zeistmanga",
                "runner": "android-gradle-unit-test",
                "members": [
                    {
                        "canonicalId": "miyorare:inventory-id:AARLAS",
                        "module": "src/id/aarlas",
                        "testClass": "compatibilityfarm.KeiyoushiAarlasParserHarnessTest",
                    }
                ],
            }
        )

        validation = validate_plan(plan, registry)
        self.assertEqual("VALID", validation["status"])
        self.assertEqual(1, validation["pendingDeclaredMembershipCount"])
        release_plan = execution_plan(plan, registry, "keiyoushi")
        self.assertNotIn(
            "miyorare:inventory-id:AARLAS",
            {entry["canonicalId"] for entry in release_plan["include"]},
        )

    def test_pending_source_cannot_claim_required_parser_coverage(self):
        broken = copy.deepcopy(self.registry)
        aarlas = next(
            source for source in broken["sources"]
            if source["canonicalId"] == "miyorare:inventory-id:AARLAS"
        )
        aarlas["compatibilityEnrollment"]["parserCoverageRequired"] = True
        with self.assertRaisesRegex(ParserFamilyPlanError, "PENDING enrollment cannot require parser coverage"):
            validate_plan(self.plan, broken)

    def test_active_source_cannot_disable_required_parser_coverage(self):
        broken = copy.deepcopy(self.registry)
        active = next(
            source for source in broken["sources"]
            if source["canonicalId"] == "miyorare:miyorare-id:KOMIKU"
        )
        active["compatibilityEnrollment"]["parserCoverageRequired"] = False
        with self.assertRaisesRegex(ParserFamilyPlanError, "ACTIVE enrollment must require parser coverage"):
            validate_plan(self.plan, broken)

    def test_asura_uses_configurable_runtime_profile_and_others_default_common(self):
        result = execution_plan(self.plan, self.registry, "keiyoushi")
        profiles = {entry["canonicalId"]: entry["runtimeProfile"] for entry in result["include"]}
        self.assertEqual("configurable", profiles["miyorare:miyorare-en:ASURASCANS"])
        for canonical_id, profile in profiles.items():
            if canonical_id != "miyorare:miyorare-en:ASURASCANS":
                self.assertEqual("common", profile)

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

    def test_runtime_profile_must_be_non_empty_string(self):
        broken = copy.deepcopy(self.plan)
        family = next(item for item in broken["families"] if item["id"] == "keiyoushi-asura-configurable")
        family["members"][0]["runtimeProfile"] = ""
        with self.assertRaisesRegex(ParserFamilyPlanError, "runtimeProfile must be a non-empty string"):
            validate_plan(broken, self.registry)

    def test_non_keiyoushi_cannot_request_optional_runtime_profile(self):
        broken = copy.deepcopy(self.plan)
        family = next(item for item in broken["families"] if item["provider"] == "uma")
        family["members"][0]["runtimeProfile"] = "configurable"
        with self.assertRaisesRegex(ParserFamilyPlanError, "runtimeProfile is only supported for keiyoushi"):
            validate_plan(broken, self.registry)


if __name__ == "__main__":
    unittest.main()
