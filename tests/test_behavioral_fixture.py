import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from behavioral_fixture import BehaviorError, run_suite, validate_suite  # noqa: E402


class BehavioralFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "compatibility/source-registry.json").read_text(encoding="utf-8"))
        cls.suite = json.loads(
            (ROOT / "compatibility/fixtures/behavioral-seed-4.json").read_text(encoding="utf-8")
        )

    def test_behavior_seed_is_valid_and_non_publishing(self):
        validate_suite(self.registry, self.suite)
        report = run_suite(self.registry, self.suite)
        self.assertEqual(report["suiteStatus"], "PASS")
        self.assertEqual(report["coverage"]["covered"], 4)
        self.assertFalse(report["parserExecution"])
        self.assertFalse(report["candidatePass"])
        self.assertFalse(report["publishEligible"])
        self.assertFalse(report["ownerActionRequired"])
        self.assertEqual(report["releaseGate"], "NOT_READY_NO_PARSER_HARNESS")

    def test_behavior_seed_exercises_required_behavior_capabilities(self):
        for fixture in self.suite["sources"]:
            self.assertEqual(
                set(fixture["cases"]),
                {"browse", "search", "details", "chapters", "content"},
            )

    def test_expected_output_mismatch_fails_without_owner_assignment(self):
        suite = copy.deepcopy(self.suite)
        suite["sources"][0]["cases"]["browse"]["expected"][0]["title"] = "Wrong title"
        report = run_suite(self.registry, suite)
        self.assertEqual(report["suiteStatus"], "FAIL")
        self.assertIn("browse", report["results"][0]["failedCapabilities"])
        self.assertEqual(report["results"][0]["failureClass"], "PARSER_FAILURE")
        self.assertFalse(report["ownerActionRequired"])
        self.assertEqual(report["releaseGate"], "BLOCKED_BEHAVIOR_FIXTURE_FAILURE")

    def test_stale_provider_baseline_fails_closed(self):
        suite = copy.deepcopy(self.suite)
        suite["sources"][1]["providerVersions"]["uma"] = "0" * 40
        report = run_suite(self.registry, suite)
        target = report["results"][1]
        self.assertEqual(target["status"], "STALE_BASELINE")
        self.assertEqual(target["failureClass"], "UPSTREAM_CHANGED")
        self.assertFalse(report["candidatePass"])

    def test_unknown_extractor_is_rejected(self):
        suite = copy.deepcopy(self.suite)
        suite["sources"][0]["cases"]["browse"]["extractor"]["kind"] = "source-specific-magic"
        with self.assertRaises(BehaviorError):
            validate_suite(self.registry, suite)

    def test_parser_execution_cannot_be_claimed_by_fixture_layer(self):
        suite = copy.deepcopy(self.suite)
        suite["parserExecution"] = True
        with self.assertRaises(BehaviorError):
            validate_suite(self.registry, suite)


if __name__ == "__main__":
    unittest.main()
