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
        self.assertEqual(aggregate["coverage"]["totalRegisteredSources"], 12)
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


if __name__ == "__main__":
    unittest.main()
