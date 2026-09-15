import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from deterministic_farm import FarmError, run_suite, validate_suite  # noqa: E402


class DeterministicFarmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / "compatibility/contract.json").read_text(encoding="utf-8"))
        cls.registry = json.loads((ROOT / "compatibility/source-registry.json").read_text(encoding="utf-8"))
        cls.suite = json.loads(
            (ROOT / "compatibility/fixtures/deterministic-seed-3.json").read_text(encoding="utf-8")
        )

    def test_seed_suite_is_valid_but_cannot_unlock_candidate(self):
        validate_suite(self.contract, self.registry, self.suite)
        report = run_suite(self.contract, self.registry, self.suite)
        self.assertEqual(report["suiteStatus"], "PASS")
        self.assertEqual(report["coverage"]["covered"], 3)
        self.assertEqual(report["coverage"]["totalRegistered"], 12)
        self.assertFalse(report["coverage"]["full"])
        self.assertFalse(report["candidatePass"])
        self.assertFalse(report["publishEligible"])
        self.assertFalse(report["ownerActionRequired"])
        self.assertEqual(report["releaseGate"], "NOT_READY_PARTIAL_COVERAGE")

    def test_fixture_bound_to_last_known_good_becomes_stale(self):
        suite = copy.deepcopy(self.suite)
        suite["sources"][0]["providerVersions"]["uma"] = "0" * 40
        report = run_suite(self.contract, self.registry, suite)
        self.assertEqual(report["suiteStatus"], "FAIL")
        self.assertEqual(report["releaseGate"], "BLOCKED_DETERMINISTIC_FAILURE")
        self.assertEqual(report["coverage"]["staleBaseline"], 1)
        self.assertEqual(report["results"][0]["failureClass"], "UPSTREAM_CHANGED")
        self.assertFalse(report["candidatePass"])

    def test_missing_contract_capability_is_rejected(self):
        suite = copy.deepcopy(self.suite)
        del suite["sources"][0]["capabilities"]["reader"]
        with self.assertRaises(FarmError):
            validate_suite(self.contract, self.registry, suite)

    def test_cookie_auth_models_expected_anonymous_auth_required(self):
        fixture = next(
            item for item in self.suite["sources"] if item["canonicalId"].endswith(":WEEBCENTRAL")
        )
        evidence = fixture["capabilities"]["authenticate"]["evidence"]
        self.assertEqual(evidence["mode"], "COOKIE")
        self.assertEqual(evidence["anonymous"], "AUTH_REQUIRED")
        self.assertEqual(evidence["credentialed"], "PASS")
        validate_suite(self.contract, self.registry, self.suite)

    def test_auth_mode_must_match_registry(self):
        suite = copy.deepcopy(self.suite)
        target = next(item for item in suite["sources"] if item["canonicalId"].endswith(":WEEBCENTRAL"))
        target["capabilities"]["authenticate"]["evidence"]["mode"] = "NO_AUTH"
        with self.assertRaises(FarmError):
            validate_suite(self.contract, self.registry, suite)

    def test_manga_content_pass_requires_every_contract_step(self):
        suite = copy.deepcopy(self.suite)
        del suite["sources"][0]["capabilities"]["content"]["evidence"]["decode"]
        with self.assertRaises(FarmError):
            validate_suite(self.contract, self.registry, suite)

    def test_failed_capability_never_becomes_candidate_pass(self):
        suite = copy.deepcopy(self.suite)
        suite["sources"][1]["capabilities"]["chapters"]["status"] = "FAIL"
        report = run_suite(self.contract, self.registry, suite)
        self.assertEqual(report["suiteStatus"], "FAIL")
        self.assertEqual(report["coverage"]["failing"], 1)
        self.assertFalse(report["candidatePass"])
        self.assertFalse(report["ownerActionRequired"])


if __name__ == "__main__":
    unittest.main()
