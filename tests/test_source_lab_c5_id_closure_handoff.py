#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("c5", ROOT / "tools/source_lab_c5_id_closure_handoff.py")
assert SPEC and SPEC.loader
c5 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c5)

SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64

def runtime(cid, provider, passed=False, message=None):
    return {
        "canonicalId": cid, "provider": provider,
        "status": "PASS" if passed else "FAIL",
        "parserExecution": True,
        "detailsTraversal": passed, "chapterTraversal": passed, "pageExtraction": passed,
        "failureType": None if passed else "org.opentest4j.AssertionFailedError",
        "failureMessage": message,
    }

def remediation():
    return {
        "schemaVersion": 1, "phase": c5.REMEDIATION_PHASE, "language": "id", "readOnly": True,
        "decisions": [
            {"canonicalId": c5.LUMOS, "decision": "LUMOS_PROVIDER_DIVERGENCE_CONFIRMED", "runtime": {"gekkoushi": runtime(c5.LUMOS, "gekkoushi", False, "browse failed"), "uma": runtime(c5.LUMOS, "uma", True)}, "safety": {"readOnly": True, "authorityMutation": False, "providerAdoption": False, "credentialInjection": False}},
            {"canonicalId": c5.MANGABALL, "decision": "MANGABALL_UPSTREAM_RUNTIME_FAILURE_CONFIRMED", "runtime": {"uma": runtime(c5.MANGABALL, "uma", False, "lastFailure=HttpStatusException")}, "safety": {"readOnly": True, "authorityMutation": False, "providerAdoption": False, "credentialInjection": False}},
            {"canonicalId": c5.SOFTKOMIK, "decision": "SOFTKOMIK_RUNTIME_FAILURE_AFTER_PUBLIC_AUTH_OVERRIDE", "runtime": {"uma": runtime(c5.SOFTKOMIK, "uma", False, "Login diperlukan untuk mengakses chapter")}, "safety": {"readOnly": True, "authorityMutation": False, "providerAdoption": False, "credentialInjection": False}},
        ],
    }

def registry(lumos_reconciled=True):
    lumos_providers = ["uma"] if lumos_reconciled else ["gekkoushi", "uma"]
    lumos_ids = {"uma": {"file":"src/main/kotlin/tsuki/site/id/LumosKomik.kt","sourceName":"LUMOSKOMIK"}}
    if not lumos_reconciled:
        lumos_ids["gekkoushi"]={"file":"src/main/kotlin/tsuki/site/madara/id/LumosKomik.kt","sourceName":"LUMOSKOMIK"}
    return {"schemaVersion": 1, "sources": [
        {"canonicalId":c5.LUMOS,"providers":lumos_providers,"upstreamIdentities":lumos_ids,"updateState":"PROMOTED","approvalState":"NOT_READY"},
        {"canonicalId":c5.MANGABALL,"providers":["uma"],"upstreamIdentities":{"uma":{"sourceName":"MANGABALL_ID"}},"updateState":"PROMOTED","approvalState":"NOT_READY"},
        {"canonicalId":c5.SOFTKOMIK,"providers":["keiyoushi","uma"],"upstreamIdentities":{},"updateState":"PENDING","approvalState":"NOT_READY"},
    ]}

def worker(lumos_approved=True):
    return {"schemaVersion": 2, "sources": {
        c5.LUMOS: {"state":"APPROVED" if lumos_approved else "READY_FOR_APPROVAL", "approvalState":"APPROVED" if lumos_approved else "WAITING_FOR_APPROVAL", "selectedProviders":["uma"]},
        c5.MANGABALL: {"state":"RETRY","approvalState":"NOT_READY","failureCategory":"HARNESS_API_MISMATCH", "evidence":{"parser":{"memberships":[{"failureMessage":"java.lang.NoSuchMethodException: old harness"}]}}},
        c5.SOFTKOMIK: {"state":"NEEDS_ATTENTION","approvalState":"NOT_READY","authType":"TOKEN"},
    }}

def meta():
    return {"runId":1,"artifactId":2,"headSha":SHA,"digest":DIGEST,"name":"artifact"}

class C5Test(unittest.TestCase):
    def build(self, reg=None, wrk=None):
        return c5.build_report(remediation(), reg or registry(), wrk or worker(), meta(), {"sourcePacksAfterRemediation":SHA,"compatibilityFarm":"c"*40})

    def test_happy_path_closes_track_with_two_operational_handoffs(self):
        report=self.build()
        self.assertTrue(report["trackCClosed"])
        self.assertEqual(report["status"],"TRACK_C_CLOSED_WITH_OPERATIONAL_HANDOFFS")
        self.assertEqual(report["summary"]["closureResolved"],3)
        self.assertEqual(report["summary"]["operationalHandoffs"],2)
        rows={r["canonicalId"]:r for r in report["decisions"]}
        self.assertEqual(rows[c5.LUMOS]["disposition"],"LUMOS_RECONCILIATION_ALREADY_SATISFIED_BY_LIFECYCLE")
        self.assertEqual(rows[c5.MANGABALL]["lifecycleCategory"],"SOURCE_PARSER_FAILURE")
        self.assertEqual(rows[c5.SOFTKOMIK]["lifecycleCategory"],"AUTH_REQUIRED")
        self.assertFalse(any(report["safetyBoundary"].values()))

    def test_unsettled_lumos_becomes_handoff_not_mutation(self):
        report=self.build(registry(False), worker(False))
        row=report["decisions"][0]
        self.assertEqual(row["disposition"],"LUMOS_PROVIDER_RECONCILIATION_LIFECYCLE_HANDOFF")
        self.assertTrue(row["operationalHandoffRequired"])
        self.assertTrue(report["trackCClosed"])

    def test_mangaball_notes_corrected_harness_supersedes_old_worker_evidence(self):
        report=self.build()
        row=next(r for r in report["decisions"] if r["canonicalId"]==c5.MANGABALL)
        self.assertTrue(row["authoritySnapshot"]["workerEvidencePredatesCorrectedHarness"])
        self.assertFalse(row["retrySemantics"]["terminal"])

    def test_softkomik_requires_real_login_evidence(self):
        bad=remediation(); bad["decisions"][2]["runtime"]["uma"]["failureMessage"]="generic failure"
        with self.assertRaises(ValueError):
            c5.build_report(bad, registry(), worker(), meta(), {"sourcePacksAfterRemediation":SHA,"compatibilityFarm":"c"*40})

    def test_softkomik_requires_auth_worker_semantics(self):
        w=worker(); w["sources"][c5.SOFTKOMIK]["authType"]="NO_AUTH"
        with self.assertRaises(ValueError):
            self.build(wrk=w)

    def test_rejects_wrong_remediation_decision(self):
        bad=remediation(); bad["decisions"][1]["decision"]="OTHER"
        with self.assertRaises(ValueError):
            c5.build_report(bad, registry(), worker(), meta(), {"sourcePacksAfterRemediation":SHA,"compatibilityFarm":"c"*40})

if __name__=="__main__":
    unittest.main()
