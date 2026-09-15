import unittest

from tools.repair_evidence import RepairEvidenceError, enrich_aggregate


class RepairEvidenceTest(unittest.TestCase):
    def aggregate(self, status="PASS"):
        return {
            "executionMode": "real-kotlin-parser-aggregate",
            "parserExecution": True,
            "suiteStatus": "PASS" if status == "PASS" else "FAIL",
            "candidatePass": False,
            "publishEligible": False,
            "ownerActionRequired": False,
            "coverage": {},
            "repairEvidence": {
                "reportedMemberships": 0,
                "validatedByRealParserRetest": 0,
                "failedRealParserRetest": 0,
            },
            "results": [
                {
                    "canonicalId": "miyorare:test",
                    "status": status,
                    "fullyExercised": True,
                    "maintenanceOutcome": "UNCHANGED",
                    "autoRepairedProviders": [],
                    "providerExecutions": [
                        {
                            "provider": "gekkoushi",
                            "status": status,
                            "tests": 1,
                            "failures": 0 if status == "PASS" else 1,
                            "maintenanceOutcome": "UNCHANGED",
                        }
                    ],
                }
            ],
        }

    def repair(self, status="APPLIED", changes=2):
        return {
            "canonicalId": "miyorare:test",
            "provider": "gekkoushi",
            "recipeId": "fixture-recipe",
            "status": status,
            "changes": changes,
            "alreadyAppliedCalls": 0,
            "beforeSha256": "before",
            "afterSha256": "after",
            "requiresRetest": True,
            "ownerActionRequired": False,
            "publishEligible": False,
        }

    def test_successful_repair_is_normalized_at_provider_and_source_level(self):
        evidence = enrich_aggregate(self.aggregate(), [self.repair()])
        source = evidence["results"][0]
        execution = source["providerExecutions"][0]

        self.assertEqual(execution["maintenanceOutcome"], "AUTO_REPAIRED")
        self.assertTrue(execution["repairEvidence"]["autoRepair"])
        self.assertTrue(execution["repairEvidence"]["retestPassed"])
        self.assertEqual(source["maintenanceOutcome"], "AUTO_REPAIRED")
        self.assertEqual(source["autoRepairedProviders"], ["gekkoushi"])
        self.assertEqual(evidence["coverage"]["autoRepairAttempts"], 1)
        self.assertEqual(evidence["coverage"]["successfulAutoRepairs"], 1)
        self.assertEqual(evidence["coverage"]["autoRepairChanges"], 2)
        self.assertEqual(evidence["repairEvidence"]["reportedMemberships"], 1)
        self.assertEqual(evidence["repairEvidence"]["validatedByRealParserRetest"], 1)
        self.assertEqual(evidence["repairEvidence"]["failedRealParserRetest"], 0)
        membership = evidence["repairEvidence"]["validatedMemberships"][0]
        self.assertEqual(membership["maintenanceOutcome"], "AUTO_REPAIRED")
        self.assertTrue(membership["retestPassed"])
        self.assertFalse(evidence["candidatePass"])
        self.assertFalse(evidence["publishEligible"])
        self.assertFalse(evidence["ownerActionRequired"])

    def test_failed_retest_is_recorded_not_hidden(self):
        evidence = enrich_aggregate(self.aggregate(status="FAIL"), [self.repair()])
        source = evidence["results"][0]
        execution = source["providerExecutions"][0]
        self.assertEqual(evidence["coverage"]["successfulAutoRepairs"], 0)
        self.assertEqual(evidence["coverage"]["failedAutoRepairRetests"], 1)
        self.assertEqual(execution["maintenanceOutcome"], "AUTO_REPAIR_RETEST_FAILED")
        self.assertFalse(execution["repairEvidence"]["retestPassed"])
        self.assertEqual(source["maintenanceOutcome"], "AUTO_REPAIR_RETEST_FAILED")
        self.assertEqual(source["autoRepairedProviders"], ["gekkoushi"])
        self.assertEqual(evidence["repairEvidence"]["failedRealParserRetest"], 1)

    def test_repair_without_parser_execution_is_rejected(self):
        repair = self.repair()
        repair["provider"] = "uma"
        with self.assertRaises(RepairEvidenceError):
            enrich_aggregate(self.aggregate(), [repair])

    def test_owner_action_repair_evidence_is_rejected(self):
        repair = self.repair()
        repair["ownerActionRequired"] = True
        with self.assertRaises(RepairEvidenceError):
            enrich_aggregate(self.aggregate(), [repair])

    def test_applied_repair_requires_a_real_change(self):
        with self.assertRaises(RepairEvidenceError):
            enrich_aggregate(self.aggregate(), [self.repair(changes=0)])

    def test_already_applied_repair_requires_zero_changes(self):
        with self.assertRaises(RepairEvidenceError):
            enrich_aggregate(self.aggregate(), [self.repair(status="ALREADY_APPLIED", changes=1)])

        evidence = enrich_aggregate(
            self.aggregate(),
            [self.repair(status="ALREADY_APPLIED", changes=0)],
        )
        self.assertEqual(evidence["coverage"]["successfulAutoRepairs"], 1)
        self.assertEqual(evidence["coverage"]["autoRepairChanges"], 0)

    def test_duplicate_aggregate_membership_is_rejected(self):
        aggregate = self.aggregate()
        duplicate = dict(aggregate["results"][0]["providerExecutions"][0])
        aggregate["results"][0]["providerExecutions"].append(duplicate)
        with self.assertRaises(RepairEvidenceError):
            enrich_aggregate(aggregate, [self.repair()])


if __name__ == "__main__":
    unittest.main()
