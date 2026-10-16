import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "evidence_scoped_disposition",
    Path(__file__).resolve().parents[1] / "tools" / "evidence_scoped_disposition.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

BASE = "0" * 40
CANDIDATE = "1" * 40
CANONICAL = "miyorare:miyorare-en:AQUAMANGA"


def intake(*, classes=None, files=None, shared=None):
    return {
        "schema": 4,
        "provider": "keiyoushi",
        "base": BASE,
        "candidate": CANDIDATE,
        "state": "hold",
        "blockingSourceCount": 1,
        "sources": [{
            "canonicalId": CANONICAL,
            "state": "review-required",
            "action": "hold-unless-reusable-adapter-supports-change",
            "automationClass": "NEEDS_REVIEW",
            "changeClasses": classes or ["parser-code-change", "shared-runtime-change"],
            "files": files or [{"path": "src/en/aquamanga/AquaManga.kt", "class": "parser-code-change"}],
            "relevantSharedRuntimeFiles": shared or ["build.gradle.kts"],
        }],
    }


def evidence(**overrides):
    record = {
        "canonicalId": CANONICAL,
        "base": BASE,
        "candidate": CANDIDATE,
        "result": "PASS",
        "disposition": "COMPATIBLE",
        "infrastructureBlocked": False,
        "evidenceType": "reviewed-compatibility-harness",
        "evidenceId": "run-123/source-aquamanga",
        "coveredChangeClasses": ["parser-code-change", "shared-runtime-change"],
        "coveredPaths": ["src/en/aquamanga/AquaManga.kt", "build.gradle.kts"],
    }
    record.update(overrides)
    return {"schema": 1, "evidence": [record]}


class EvidenceScopedDispositionTests(unittest.TestCase):
    def test_exact_provenance_and_complete_impact_can_resolve_review(self):
        result = MODULE.apply_dispositions(intake(), evidence())
        source = result["sources"][0]
        self.assertEqual("REVIEWED_COMPATIBLE", source["automationClass"])
        self.assertEqual("reviewed-compatible", source["state"])
        self.assertEqual("clear", result["state"])
        self.assertEqual(0, result["blockingSourceCount"])

    def test_candidate_mismatch_stays_held(self):
        result = MODULE.apply_dispositions(intake(), evidence(candidate="2" * 40))
        self.assertEqual("NEEDS_REVIEW", result["sources"][0]["automationClass"])
        self.assertEqual("hold", result["state"])

    def test_baseline_mismatch_stays_held(self):
        result = MODULE.apply_dispositions(intake(), evidence(base="2" * 40))
        self.assertEqual("NEEDS_REVIEW", result["sources"][0]["automationClass"])

    def test_missing_changed_path_stays_held(self):
        result = MODULE.apply_dispositions(
            intake(), evidence(coveredPaths=["src/en/aquamanga/AquaManga.kt"])
        )
        self.assertEqual("NEEDS_REVIEW", result["sources"][0]["automationClass"])

    def test_missing_change_class_stays_held(self):
        result = MODULE.apply_dispositions(
            intake(), evidence(coveredChangeClasses=["parser-code-change"])
        )
        self.assertEqual("NEEDS_REVIEW", result["sources"][0]["automationClass"])

    def test_failed_evidence_stays_held(self):
        result = MODULE.apply_dispositions(intake(), evidence(result="FAIL"))
        self.assertEqual("NEEDS_REVIEW", result["sources"][0]["automationClass"])

    def test_infrastructure_blocked_evidence_stays_held(self):
        result = MODULE.apply_dispositions(intake(), evidence(infrastructureBlocked=True))
        self.assertEqual("NEEDS_REVIEW", result["sources"][0]["automationClass"])

    def test_unknown_or_uncovered_new_impact_reholds_candidate(self):
        source_intake = intake(
            classes=["parser-code-change", "shared-runtime-change", "module-resource-or-structure-change"],
            files=[
                {"path": "src/en/aquamanga/AquaManga.kt", "class": "parser-code-change"},
                {"path": "src/en/aquamanga/new.json", "class": "module-resource-or-structure-change"},
            ],
        )
        result = MODULE.apply_dispositions(source_intake, evidence())
        self.assertEqual("NEEDS_REVIEW", result["sources"][0]["automationClass"])
        self.assertEqual("hold", result["state"])

    def test_evidence_for_other_identity_cannot_cross_apply(self):
        result = MODULE.apply_dispositions(
            intake(), evidence(canonicalId="miyorare:inventory-en:AQUAMANGA")
        )
        self.assertEqual("NEEDS_REVIEW", result["sources"][0]["automationClass"])

    def test_nonblocking_existing_source_is_not_reclassified(self):
        source_intake = intake()
        source_intake["sources"][0]["automationClass"] = "AUTO-REPAIRABLE"
        source_intake["sources"][0]["state"] = "dependency-validation-required"
        source_intake["blockingSourceCount"] = 0
        source_intake["state"] = "clear"
        result = MODULE.apply_dispositions(source_intake, evidence())
        self.assertEqual("AUTO-REPAIRABLE", result["sources"][0]["automationClass"])
        self.assertNotIn("evidenceDisposition", result["sources"][0])


if __name__ == "__main__":
    unittest.main()
