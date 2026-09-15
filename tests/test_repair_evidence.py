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
            "results": [
                {
                    "canonicalId": "miyorare:test",
                    "providerExecutions": [
                        {"provider": "gekkoushi", "status": status, "tests": 1, "failures": 0}
                    ],
                }
            ],
        }

    def repair(self):
        return {
            "canonicalId": "miyorare:test",
            "provider": "gekkoushi",
            "recipeId": "fixture-recipe",
            "status": "APPLIED",
            "changes": 2,
            "beforeSha256": "before",
            "afterSha256": "after",
            "requiresRetest": True,
            "ownerActionRequired": False,
            "publishEligible": False,
        }

    def test_successful_repair_is_attached_to_matching_passed_retest(self):
        evidence = enrich_aggregate(self.aggregate(), [self.repair()])
        execution = evidence["results"][0]["providerExecutions"][0]
        self.assertTrue(execution["repairEvidence"]["autoRepair"])
        self.assertTrue(execution["repairEvidence"]["retestPassed"])
        self.assertEqual(evidence["coverage"]["autoRepairAttempts"], 1)
        self.assertEqual(evidence["coverage"]["successfulAutoRepairs"], 1)
        self.assertEqual(evidence["coverage"]["autoRepairChanges"], 2)
        self.assertFalse(evidence["publishEligible"])
        self.assertFalse(evidence["ownerActionRequired"])

    def test_failed_retest_is_recorded_not_hidden(self):
        evidence = enrich_aggregate(self.aggregate(status="FAIL"), [self.repair()])
        self.assertEqual(evidence["coverage"]["successfulAutoRepairs"], 0)
        self.assertEqual(evidence["coverage"]["failedAutoRepairRetests"], 1)
        self.assertFalse(evidence["results"][0]["providerExecutions"][0]["repairEvidence"]["retestPassed"])

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


if __name__ == "__main__":
    unittest.main()
