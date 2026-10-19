from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_lab_b3_targeted_runtime", ROOT / "tools" / "source_lab_b3_targeted_runtime.py"
)
b3 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(b3)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def b2_report() -> dict:
    return {
        "summary": {"batch3Rows": 2},
        "decisions": [
            {
                "canonicalId": "miyorare:inventory-en:ALPHA",
                "displayName": "Alpha Scans",
                "decision": {"nextPhase": "TRACK_B_BATCH_3", "decision": "B3_PRIMARY_COVERAGE_DECISION_REQUIRED"},
                "providers": {
                    "uma": {"farmIdentity": None},
                    "gekkoushi": {"farmIdentity": None},
                    "keiyoushi": {"farmIdentity": {"module": "src/en/alpha", "sourceName": "Alpha Scans", "sourceId": 1}},
                },
            },
            {
                "canonicalId": "miyorare:inventory-en:BETA",
                "displayName": "Beta",
                "decision": {"nextPhase": "TRACK_B_BATCH_3", "decision": "B3_VALIDATE_PRIMARY_BEFORE_IGNORING_REFERENCE_GAP"},
                "providers": {
                    "uma": {"farmIdentity": None},
                    "gekkoushi": {"farmIdentity": {"file": "src/main/kotlin/Beta.kt", "sourceName": "BETA"}},
                    "keiyoushi": {"farmIdentity": {"module": "src/en/beta", "sourceName": "Beta", "sourceId": 2}},
                },
            },
        ],
    }


def profile(cid: str, provider: str, *, passed: bool, detail: str = "URLError") -> dict:
    return {
        "results": [{
            "canonicalId": cid,
            "state": "PARSER_PENDING" if passed else "RETRY",
            "failureCategory": None if passed else "PROFILE_TRANSIENT",
            "evidence": {
                "profile": {
                    "gate": "PASS" if passed else "FAIL",
                    "selectedProviders": [provider] if passed else [],
                    "memberships": [{
                        "provider": provider,
                        "profilePass": passed,
                        "probe": {"reachable": passed, "detail": detail},
                    }],
                }
            },
        }]
    }


class Batch3Test(unittest.TestCase):
    def test_exact_reference_host_discovers_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "kei/src/en/alpha/Alpha.kt", 'val baseUrl = "https://alpha.example"')
            write(root / "uma/src/main/kotlin/Random.kt", 'val baseUrl = "https://alpha.example"')
            write(root / "gek/src/main/kotlin/Beta.kt", 'val baseUrl = "https://beta.example"')
            plan = b3.build_plan(
                b2_report(),
                {"uma": root / "uma", "gekkoushi": root / "gek"},
                {"uma": root / "uma", "gekkoushi": root / "gek"},
                root / "kei",
                candidate_commits={"uma": "u" * 40, "gekkoushi": "g" * 40},
                lkg_commits={"uma": "l" * 40, "gekkoushi": "k" * 40},
            )
            alpha = plan["items"][0]
            self.assertEqual(alpha["candidate"]["uma"]["state"], "BOUND_DISCOVERED_IDENTITY")
            self.assertEqual(alpha["candidate"]["uma"]["identity"]["file"], "src/main/kotlin/Random.kt")

    def test_existing_identity_is_preferred_when_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "kei/src/en/beta/Beta.kt", 'val baseUrl = "https://beta.example"')
            write(root / "gek/src/main/kotlin/Beta.kt", 'val baseUrl = "https://beta.example"')
            plan = b3.build_plan(
                b2_report(),
                {"uma": root / "uma", "gekkoushi": root / "gek"},
                {"uma": root / "uma", "gekkoushi": root / "gek"},
                root / "kei",
                candidate_commits={"uma": "u" * 40, "gekkoushi": "g" * 40},
                lkg_commits={"uma": "l" * 40, "gekkoushi": "k" * 40},
            )
            beta = plan["items"][1]
            self.assertEqual(beta["candidate"]["gekkoushi"]["state"], "BOUND_EXISTING_IDENTITY")

    def test_ambiguous_discovery_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fingerprint = {"aliases": ["ALPHA"], "host": "alpha.example"}
            write(root / "src/A.kt", 'val baseUrl = "https://alpha.example"')
            write(root / "src/B.kt", 'val baseUrl = "https://alpha.example"')
            found = b3.discover_primary(root, fingerprint)
            self.assertEqual(found["state"], "AMBIGUOUS")

    def test_runtime_plan_contains_only_bound_primary(self) -> None:
        plan = {
            "items": [{
                "canonicalId": "x",
                "candidate": {
                    "uma": {"identity": {"file": "src/X.kt", "sourceName": "X"}},
                    "gekkoushi": {"identity": None},
                },
            }]
        }
        runtime = b3.runtime_plan(plan, "candidate")
        self.assertEqual(runtime["count"], 1)
        self.assertEqual(runtime["items"][0]["providers"], ["uma"])

    def test_candidate_pass_routes_to_batch4_without_mutation(self) -> None:
        plan = {
            "cohortSha256": "d",
            "candidateCommits": {},
            "lkgCommits": {},
            "items": [{
                "canonicalId": "x",
                "displayName": "X",
                "reference": {},
                "candidate": {
                    "uma": {"identity": {"file": "src/X.kt"}},
                    "gekkoushi": {"identity": None},
                },
                "lkg": {
                    "uma": {"identity": None},
                    "gekkoushi": {"identity": None},
                },
            }],
        }
        passed = {
            "results": [{
                "canonicalId": "x", "provider": "uma", "status": "PASS",
                "parserExecution": True, "detailsTraversal": True,
                "chapterTraversal": True, "pageExtraction": True,
            }]
        }
        report = b3.build_report(plan, passed, {"results": []})
        row = report["decisions"][0]
        self.assertEqual(row["decision"], "B4_CANDIDATE_RUNTIME_PROVEN")
        self.assertTrue(row["safety"]["readOnly"])
        self.assertFalse(row["safety"]["mutateLastKnownGood"])

    def test_lkg_pass_candidate_fail_is_regression(self) -> None:
        binding = {"identity": {"file": "src/X.kt"}}
        failed = {"status": "FAIL", "parserExecution": True}
        passed = {
            "status": "PASS", "parserExecution": True, "detailsTraversal": True,
            "chapterTraversal": True, "pageExtraction": True,
        }
        row = b3.classify_provider(binding, binding, failed, passed)
        self.assertEqual(row["state"], "CANDIDATE_REGRESSION")

    def test_profile_failure_is_preserved_when_parser_did_not_run(self) -> None:
        binding = {"identity": {"file": "src/X.kt"}}
        candidate_profile = b3.profile_map(profile("x", "gekkoushi", passed=False))
        lkg_profile = b3.profile_map(profile("x", "gekkoushi", passed=False, detail="TimeoutError"))
        row = b3.classify_provider(
            binding,
            binding,
            None,
            None,
            candidate_profile[("x", "gekkoushi")],
            lkg_profile[("x", "gekkoushi")],
        )
        self.assertEqual(row["state"], "BOTH_PROFILE_BLOCKED")
        self.assertEqual(row["candidateProfile"]["failureCategory"], "PROFILE_TRANSIENT")
        self.assertEqual(row["candidateProfile"]["membership"]["probe"]["detail"], "URLError")
        self.assertEqual(row["lkgProfile"]["membership"]["probe"]["detail"], "TimeoutError")

    def test_identical_runtime_failures_are_explicit(self) -> None:
        binding = {"identity": {"file": "src/X.kt"}}
        failed = {
            "status": "FAIL",
            "parserExecution": True,
            "detailsTraversal": False,
            "chapterTraversal": False,
            "pageExtraction": False,
            "failureType": "ParseException",
            "failureMessage": "browse failed",
        }
        row = b3.classify_provider(binding, binding, failed, dict(failed))
        self.assertEqual(row["state"], "BOTH_RUNTIME_FAILING")
        self.assertTrue(row["sameRuntimeFailure"])

    def test_b3_cohort_count_is_fail_closed(self) -> None:
        report = b2_report()
        report["summary"]["batch3Rows"] = 33
        with self.assertRaises(ValueError):
            b3.b3_rows(report)


if __name__ == "__main__":
    unittest.main()
