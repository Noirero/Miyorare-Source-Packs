import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from parser_harness_aggregate import AggregateError, aggregate_reports  # noqa: E402


class ParserHarnessAggregateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "compatibility/source-registry.json").read_text(encoding="utf-8"))
        cls.plan = json.loads((ROOT / "compatibility/parser-families.json").read_text(encoding="utf-8"))

    @staticmethod
    def report(provider, *sources):
        return {
            "executionMode": "real-kotlin-parser",
            "parserExecution": True,
            "provider": provider,
            "results": [
                {
                    "canonicalId": source,
                    "provider": provider,
                    "parserExecution": True,
                    "status": "PASS",
                    "testClass": f"fixture.{source.split(':')[-1]}",
                    "tests": 1,
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                }
                for source in sources
            ],
        }

    @staticmethod
    def repair(provider, canonical_id):
        return {
            "schemaVersion": 1,
            "recipeId": "forward-parser-request-headers-to-http-get",
            "provider": provider,
            "canonicalId": canonical_id,
            "sourcePath": "_upstream/provider/Source.kt",
            "status": "APPLIED",
            "changes": 5,
            "alreadyAppliedCalls": 0,
            "beforeSha256": "a" * 64,
            "afterSha256": "b" * 64,
            "ownerActionRequired": False,
            "publishEligible": False,
            "requiresRetest": True,
        }

    def required_sources(self, registry=None):
        registry = registry or self.registry
        return [
            source for source in registry["sources"]
            if source.get("compatibilityEnrollment", {}).get("parserCoverageRequired", True)
        ]

    def planned_reports(self):
        grouped = {}
        for family in self.plan["families"]:
            grouped.setdefault(family["provider"], [])
            grouped[family["provider"]].extend(member["canonicalId"] for member in family["members"])
        return [
            self.report(provider, *sorted(canonical_ids))
            for provider, canonical_ids in sorted(grouped.items())
        ]

    def test_pending_source_is_excluded_but_full_active_coverage_passes(self):
        aggregate = aggregate_reports(self.registry, self.planned_reports())
        coverage = aggregate["coverage"]
        required_sources = self.required_sources()
        required_memberships = sum(len(source["providers"]) for source in required_sources)

        self.assertEqual(len(self.registry["sources"]), coverage["totalRegisteredSources"])
        self.assertEqual(len(required_sources), coverage["requiredCanonicalSources"])
        self.assertEqual(len(self.registry["sources"]) - len(required_sources), coverage["pendingCanonicalSources"])
        self.assertEqual(len(required_sources), coverage["canonicalExecuted"])
        self.assertEqual(required_memberships, coverage["totalProviderMemberships"])
        self.assertEqual(required_memberships, coverage["providerMembershipsExecuted"])
        self.assertEqual(0, coverage["missingProviderMemberships"])
        self.assertEqual(0, coverage["failingProviderMemberships"])
        self.assertTrue(coverage["fullCanonicalCoverage"])
        self.assertTrue(coverage["fullProviderMembershipCoverage"])
        self.assertTrue(aggregate["candidatePass"])
        self.assertEqual("REAL_PARSER_READY", aggregate["releaseGate"])
        self.assertNotIn(
            "miyorare:inventory-id:AARLAS",
            {item["canonicalId"] for item in aggregate["results"]},
        )

    def test_activating_aarlas_without_real_harness_stays_partial_not_pass(self):
        registry = copy.deepcopy(self.registry)
        aarlas = next(
            source for source in registry["sources"]
            if source["canonicalId"] == "miyorare:inventory-id:AARLAS"
        )
        previous_required_sources = self.required_sources(registry)
        previous_memberships = sum(len(source["providers"]) for source in previous_required_sources)
        aarlas["compatibilityEnrollment"] = {
            "state": "ACTIVE",
            "parserCoverageRequired": True,
        }
        aggregate = aggregate_reports(registry, self.planned_reports())
        coverage = aggregate["coverage"]
        self.assertEqual(len(previous_required_sources) + 1, coverage["requiredCanonicalSources"])
        self.assertEqual(previous_memberships + len(aarlas["providers"]), coverage["totalProviderMemberships"])
        self.assertEqual(previous_memberships, coverage["providerMembershipsExecuted"])
        self.assertEqual(len(aarlas["providers"]), coverage["missingProviderMemberships"])
        self.assertFalse(aggregate["candidatePass"])
        self.assertEqual("NOT_READY_PARTIAL_PARSER_HARNESS", aggregate["releaseGate"])

    def test_pending_source_parser_result_is_rejected(self):
        with self.assertRaisesRegex(AggregateError, "PENDING/non-required membership"):
            aggregate_reports(
                self.registry,
                self.planned_reports() + [self.report("keiyoushi", "miyorare:inventory-id:AARLAS")],
            )

    def test_partial_cross_provider_evidence_stays_non_publishable(self):
        aggregate = aggregate_reports(
            self.registry,
            [
                self.report("uma", "miyorare:miyorare-id:KOMIKU", "miyorare:miyorare-id:SHINIGAMI"),
                self.report("gekkoushi", "miyorare:miyorare-id:DOUJINDESU"),
            ],
        )
        self.assertEqual(aggregate["suiteStatus"], "PASS")
        self.assertEqual(aggregate["coverage"]["canonicalExecuted"], 3)
        self.assertEqual(aggregate["coverage"]["totalRegisteredSources"], len(self.registry["sources"]))
        self.assertEqual(aggregate["coverage"]["requiredCanonicalSources"], len(self.required_sources()))
        self.assertEqual(aggregate["repairEvidence"]["reportedMemberships"], 0)
        self.assertFalse(aggregate["candidatePass"])
        self.assertFalse(aggregate["publishEligible"])
        self.assertFalse(aggregate["ownerActionRequired"])
        self.assertEqual(aggregate["releaseGate"], "NOT_READY_PARTIAL_PARSER_HARNESS")

        komiku = next(x for x in aggregate["results"] if x["canonicalId"].endswith(":KOMIKU"))
        self.assertIn("keiyoushi", komiku["missingProviders"])
        self.assertEqual(komiku["status"], "PARTIAL")

    def test_provider_failure_blocks_aggregate(self):
        report = self.report("uma", "miyorare:miyorare-id:KOMIKU")
        report["results"][0]["status"] = "FAIL"
        report["results"][0]["failures"] = 1
        aggregate = aggregate_reports(self.registry, [report])
        self.assertEqual(aggregate["suiteStatus"], "FAIL")
        self.assertEqual(aggregate["releaseGate"], "BLOCKED_REAL_PARSER_FAILURE")
        self.assertFalse(aggregate["candidatePass"])

    def test_wrong_provider_membership_is_rejected(self):
        report = self.report("gekkoushi", "miyorare:miyorare-en:WEEBCENTRAL")
        with self.assertRaises(AggregateError):
            aggregate_reports(self.registry, [report])

    def test_duplicate_membership_is_rejected(self):
        a = self.report("uma", "miyorare:miyorare-id:KOMIKU")
        b = self.report("uma", "miyorare:miyorare-id:KOMIKU")
        with self.assertRaises(AggregateError):
            aggregate_reports(self.registry, [a, b])

    def test_auto_repair_is_bound_to_membership_and_real_parser_retest(self):
        canonical_id = "miyorare:miyorare-id:SHINIGAMI"
        aggregate = aggregate_reports(
            self.registry,
            [
                self.report("uma", canonical_id),
                self.report("gekkoushi", canonical_id),
            ],
            [self.repair("gekkoushi", canonical_id)],
        )
        self.assertEqual(aggregate["repairEvidence"]["reportedMemberships"], 1)
        self.assertEqual(aggregate["repairEvidence"]["validatedByRealParserRetest"], 1)
        self.assertEqual(aggregate["repairEvidence"]["failedRealParserRetest"], 0)

        source = next(x for x in aggregate["results"] if x["canonicalId"] == canonical_id)
        self.assertEqual(source["status"], "PASS")
        self.assertTrue(source["fullyExercised"])
        self.assertEqual(source["maintenanceOutcome"], "AUTO_REPAIRED")
        self.assertEqual(source["autoRepairedProviders"], ["gekkoushi"])
        execution = next(x for x in source["providerExecutions"] if x["provider"] == "gekkoushi")
        self.assertEqual(execution["maintenanceOutcome"], "AUTO_REPAIRED")
        self.assertTrue(execution["repairEvidence"]["retestValidated"])
        self.assertEqual(execution["repairEvidence"]["changes"], 5)

    def test_repair_without_real_parser_retest_is_rejected(self):
        canonical_id = "miyorare:miyorare-id:SHINIGAMI"
        with self.assertRaises(AggregateError):
            aggregate_reports(
                self.registry,
                [self.report("uma", canonical_id)],
                [self.repair("gekkoushi", canonical_id)],
            )

    def test_repair_that_requires_owner_action_is_rejected(self):
        canonical_id = "miyorare:miyorare-id:SHINIGAMI"
        repair = self.repair("gekkoushi", canonical_id)
        repair["ownerActionRequired"] = True
        with self.assertRaises(AggregateError):
            aggregate_reports(
                self.registry,
                [self.report("gekkoushi", canonical_id)],
                [repair],
            )


if __name__ == "__main__":
    unittest.main()
