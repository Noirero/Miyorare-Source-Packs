#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "remediation", ROOT / "tools" / "source_lab_c3_id_remediation.py"
)
assert SPEC and SPEC.loader
remediation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remediation)


def c2() -> dict:
    def provider(identity=None, **extra):
        return {"inventoryIdentity": identity, "farmIdentity": identity, **extra}
    return {
        "phase": remediation.C2_PHASE,
        "readOnly": True,
        "language": "id",
        "provenance": {"controlCommit": "1" * 40},
        "sourceAssessments": [
            {
                "canonicalId": remediation.LUMOS,
                "providers": {
                    "gekkoushi": provider({"file": "g/Lumos.kt", "sourceName": "LUMOSKOMIK"}),
                    "uma": provider({"file": "u/Lumos.kt", "sourceName": "LUMOSKOMIK"}),
                    "keiyoushi": provider({"module": "src/id/lumoskomik", "baseUrl": "https://03.lumosgg.com"}),
                },
            },
            {
                "canonicalId": remediation.MANGABALL,
                "providers": {
                    "uma": provider({"file": "u/Mangaball.kt", "sourceName": "MANGABALL_ID"}),
                },
            },
            {
                "canonicalId": remediation.SOFTKOMIK,
                "providers": {
                    "uma": provider({"file": "u/Soft.kt", "sourceName": "SOFTKOMIK"}),
                    "keiyoushi": provider({"module": "src/id/softkomik", "baseUrl": "https://softkomik.co"}),
                },
            },
        ],
    }


def c3() -> dict:
    return {
        "phase": remediation.C3_PHASE,
        "readOnly": True,
        "provenance": {},
        "summary": {"remediationRequired": 3},
        "decisions": [
            {"canonicalId": cid, "decision": "OLD", "runtimeState": "OLD", "nextAction": "C3_REMEDIATION_REQUIRED"}
            for cid in remediation.REMEDIATION_IDS
        ],
    }


def c4() -> dict:
    return {
        "phase": remediation.C4_PHASE,
        "readOnly": True,
        "baselineRefs": {},
        "remediation": {
            "remainingRows": 3,
            "canonicalIds": list(remediation.REMEDIATION_IDS),
        },
    }


def runtime(cid: str, provider: str, passed: bool) -> dict:
    return {
        "canonicalId": cid,
        "provider": provider,
        "status": "PASS" if passed else "FAIL",
        "parserExecution": True,
        "detailsTraversal": passed,
        "chapterTraversal": passed,
        "pageExtraction": passed,
    }


class RemediationTest(unittest.TestCase):
    def build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "g").mkdir()
            (root / "u").mkdir()
            (root / "g/Lumos.kt").write_text(
                'class X { val x = MadaraParser(ctx, src, "lumos01.com") }', encoding="utf-8"
            )
            (root / "u/Lumos.kt").write_text(
                'val x = ConfigKey.Domain("03.lumosgg.com")', encoding="utf-8"
            )
            (root / "u/Mangaball.kt").write_text("class M", encoding="utf-8")
            (root / "u/Soft.kt").write_text("class S", encoding="utf-8")
            return remediation.build_plan(c2(), c3(), c4(), uma_root=root, gekkoushi_root=root)

    def test_plan_is_only_three_sources_and_soft_override_is_explicit(self):
        plan, runtime_plan = self.build()
        self.assertEqual(plan["count"], 3)
        self.assertEqual(runtime_plan["count"], 3)
        rows = {x["canonicalId"]: x for x in plan["items"]}
        self.assertEqual(rows[remediation.LUMOS]["providers"], ["gekkoushi", "uma"])
        self.assertTrue(rows[remediation.SOFTKOMIK]["allowUnauthenticatedLiveSmoke"])
        self.assertEqual(rows[remediation.SOFTKOMIK]["authOverrideScope"], "PUBLIC_BROWSE_ONLY_NO_CREDENTIALS")
        self.assertFalse(plan["safetyBoundary"]["injectCredentials"])

    def test_plan_records_lumos_domain_divergence(self):
        plan, _ = self.build()
        evidence = plan["structuralEvidence"]["lumos"]
        self.assertEqual(evidence["gekkoushiDomain"], "lumos01.com")
        self.assertEqual(evidence["umaDomain"], "03.lumosgg.com")
        self.assertEqual(evidence["keiyoushiBaseUrl"], "https://03.lumosgg.com")

    def test_prepare_profiles_only_overrides_explicit_source(self):
        plan, _ = self.build()
        profiles = {"results": [
            {"canonicalId": remediation.SOFTKOMIK, "authType": "TOKEN", "state": "PARSER_PENDING"},
            {"canonicalId": remediation.MANGABALL, "authType": "TOKEN", "state": "PARSER_PENDING"},
        ]}
        adjusted = remediation.prepare_profiles(plan, profiles)
        rows = {x["canonicalId"]: x for x in adjusted["results"]}
        self.assertEqual(rows[remediation.SOFTKOMIK]["authType"], "NO_AUTH")
        self.assertEqual(rows[remediation.SOFTKOMIK]["originalAuthType"], "TOKEN")
        self.assertTrue(rows[remediation.SOFTKOMIK]["authSmokeOverride"])
        self.assertEqual(rows[remediation.MANGABALL]["authType"], "TOKEN")

    def test_lumos_alternate_pass_closes_c3_row_but_requires_handoff(self):
        plan, _ = self.build()
        results = {"results": [
            runtime(remediation.LUMOS, "gekkoushi", False),
            runtime(remediation.LUMOS, "uma", True),
            runtime(remediation.MANGABALL, "uma", False),
            runtime(remediation.SOFTKOMIK, "uma", True),
        ]}
        report = remediation.build_report(plan, results)
        rows = {x["canonicalId"]: x for x in report["decisions"]}
        self.assertEqual(rows[remediation.LUMOS]["decision"], "LUMOS_PROVIDER_DIVERGENCE_CONFIRMED")
        self.assertTrue(rows[remediation.LUMOS]["remediationResolved"])
        self.assertTrue(rows[remediation.LUMOS]["lifecycleHandoffRequired"])
        self.assertEqual(report["summary"]["remaining"], 1)
        self.assertFalse(report["trackCClosed"])

    def test_all_runtime_passes_still_do_not_auto_adopt(self):
        plan, _ = self.build()
        results = {"results": [
            runtime(remediation.LUMOS, "gekkoushi", True),
            runtime(remediation.LUMOS, "uma", True),
            runtime(remediation.MANGABALL, "uma", True),
            runtime(remediation.SOFTKOMIK, "uma", True),
        ]}
        report = remediation.build_report(plan, results)
        self.assertEqual(report["summary"]["remaining"], 0)
        self.assertEqual(report["summary"]["lifecycleHandoffs"], 3)
        self.assertFalse(report["trackCClosed"])
        self.assertFalse(report["safetyBoundary"]["autoAdoptProvider"])

    def test_boundary_drift_fails_closed(self):
        bad = c4()
        bad["remediation"]["canonicalIds"] = [remediation.LUMOS]
        with self.assertRaises(ValueError):
            remediation.validate_boundary(c2(), c3(), bad)


if __name__ == "__main__":
    unittest.main()
