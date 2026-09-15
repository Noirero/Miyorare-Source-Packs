import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from parser_harness_report import HarnessReportError, build_report, read_junit_results  # noqa: E402


class ParserHarnessReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "compatibility/source-registry.json").read_text(encoding="utf-8"))

    def test_partial_real_parser_pass_stays_non_publishable(self):
        junit = {
            "compatibilityfarm.KomikuParserHarnessTest": {
                "tests": 1,
                "failures": 0,
                "errors": 0,
                "skipped": 0,
            }
        }
        report = build_report(
            self.registry,
            junit,
            "uma",
            [("miyorare:miyorare-id:KOMIKU", "compatibilityfarm.KomikuParserHarnessTest")],
        )
        self.assertTrue(report["parserExecution"])
        self.assertEqual(report["suiteStatus"], "PASS")
        self.assertEqual(report["coverage"]["parserExecuted"], 1)
        self.assertEqual(report["coverage"]["totalRegistered"], 12)
        self.assertFalse(report["candidatePass"])
        self.assertFalse(report["publishEligible"])
        self.assertFalse(report["ownerActionRequired"])
        self.assertEqual(report["releaseGate"], "NOT_READY_PARTIAL_PARSER_HARNESS")

    def test_real_parser_failure_blocks(self):
        junit = {
            "compatibilityfarm.KomikuParserHarnessTest": {
                "tests": 1,
                "failures": 1,
                "errors": 0,
                "skipped": 0,
            }
        }
        report = build_report(
            self.registry,
            junit,
            "uma",
            [("miyorare:miyorare-id:KOMIKU", "compatibilityfarm.KomikuParserHarnessTest")],
        )
        self.assertEqual(report["suiteStatus"], "FAIL")
        self.assertEqual(report["releaseGate"], "BLOCKED_REAL_PARSER_FAILURE")
        self.assertFalse(report["candidatePass"])

    def test_unregistered_source_is_rejected(self):
        junit = {"example.Test": {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}}
        with self.assertRaises(HarnessReportError):
            build_report(self.registry, junit, "uma", [("missing:source", "example.Test")])

    def test_reads_gradle_junit_xml(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "TEST-compatibilityfarm.KomikuParserHarnessTest.xml"
            path.write_text(
                '<testsuite name="compatibilityfarm.KomikuParserHarnessTest" tests="1" skipped="0" failures="0" errors="0"></testsuite>',
                encoding="utf-8",
            )
            result = read_junit_results(Path(temp))
        self.assertEqual(result["compatibilityfarm.KomikuParserHarnessTest"]["tests"], 1)


if __name__ == "__main__":
    unittest.main()
