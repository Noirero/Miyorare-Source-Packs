import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "runtime_closure_evidence", Path(__file__).resolve().parents[1] / "tools" / "runtime_closure_evidence.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

BASE = "0" * 40
CANDIDATE = "1" * 40
CANONICAL = "miyorare:miyorare-en:AQUAMANGA"


def intake():
    return {"schema": 4, "base": BASE, "candidate": CANDIDATE, "sources": [{
        "canonicalId": CANONICAL, "automationClass": "NEEDS_REVIEW",
        "changeClasses": ["parser-code-change", "shared-runtime-change"],
        "files": [{"path": "src/en/aquamanga/AquaManga.kt", "class": "parser-code-change"}],
        "relevantSharedRuntimeFiles": ["build.gradle.kts"],
    }]}


def execution(**overrides):
    proof = {
        "canonicalId": CANONICAL, "result": "PASS", "infrastructureBlocked": False,
        "candidateRevision": CANDIDATE, "runtimeClosureRevision": CANDIDATE,
        "evidenceId": "run-1/aquamanga", "requiresAndroidWebView": False,
        "androidWebViewExecutionProven": False,
        "executedRuntimeClosurePaths": ["src/en/aquamanga/AquaManga.kt", "build.gradle.kts"],
        "exercisedChangeClasses": ["parser-code-change", "shared-runtime-change"],
    }
    proof.update(overrides)
    return {"schema": 1, "base": BASE, "candidate": CANDIDATE, "proofs": [proof]}


class RuntimeClosureEvidenceTests(unittest.TestCase):
    def test_complete_execution_proof_emits_contract_record(self):
        result = MODULE.derive(intake(), execution())
        self.assertEqual(1, len(result["evidence"]))
        self.assertEqual("COMPATIBLE", result["evidence"][0]["disposition"])

    def test_missing_runtime_path_emits_no_record(self):
        result = MODULE.derive(intake(), execution(executedRuntimeClosurePaths=["src/en/aquamanga/AquaManga.kt"]))
        self.assertEqual([], result["evidence"])

    def test_missing_change_class_emits_no_record(self):
        result = MODULE.derive(intake(), execution(exercisedChangeClasses=["parser-code-change"]))
        self.assertEqual([], result["evidence"])

    def test_candidate_mismatch_emits_no_record(self):
        result = MODULE.derive(intake(), execution(candidateRevision="2" * 40))
        self.assertEqual([], result["evidence"])

    def test_runtime_revision_mismatch_emits_no_record(self):
        result = MODULE.derive(intake(), execution(runtimeClosureRevision="2" * 40))
        self.assertEqual([], result["evidence"])

    def test_failed_or_blocked_execution_emits_no_record(self):
        self.assertEqual([], MODULE.derive(intake(), execution(result="FAIL"))["evidence"])
        self.assertEqual([], MODULE.derive(intake(), execution(infrastructureBlocked=True))["evidence"])

    def test_webview_requirement_fails_closed_without_android_execution(self):
        result = MODULE.derive(intake(), execution(requiresAndroidWebView=True, androidWebViewExecutionProven=False))
        self.assertEqual([], result["evidence"])

    def test_webview_requirement_accepts_explicit_android_execution(self):
        result = MODULE.derive(intake(), execution(requiresAndroidWebView=True, androidWebViewExecutionProven=True))
        self.assertEqual(1, len(result["evidence"]))

    def test_top_level_provenance_mismatch_emits_no_record(self):
        data = execution()
        data["candidate"] = "2" * 40
        self.assertEqual([], MODULE.derive(intake(), data)["evidence"])


if __name__ == "__main__":
    unittest.main()
