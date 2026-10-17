from pathlib import Path
import copy
import unittest

from tools.bind_batcave_android_webview_evidence import CANONICAL, bind


ROOT = Path(__file__).resolve().parents[1]
BASE = "2025891752e4705effc28e87a043f7205014cde3"
CANDIDATE = "23345ef345e3b20d7fcc0b5d8fdc922d025af47f"
MIYORARE = "812cfd2567afa9b5517ce639620b002271a09c95"


def runtime_report() -> dict:
    return {
        "schema": 1,
        "base": BASE,
        "candidate": CANDIDATE,
        "proofs": [
            {
                "canonicalId": CANONICAL,
                "result": "PASS",
                "infrastructureBlocked": True,
                "baseRevision": BASE,
                "candidateRevision": CANDIDATE,
                "runtimeClosureRevision": CANDIDATE,
                "evidenceId": f"github-run:1:{CANONICAL}",
                "requiresAndroidWebView": True,
                "androidWebViewExecutionProven": False,
                "executedRuntimeClosurePaths": ["src/en/batcave/build.gradle.kts"],
                "exercisedChangeClasses": ["build-definition-change"],
            }
        ],
    }


def android_probe() -> dict:
    return {
        "schema": 1,
        "canonicalId": CANONICAL,
        "candidateRevision": CANDIDATE,
        "miyorareRevision": MIYORARE,
        "workflowRunId": 12345,
        "runtime": "miyorare-android-instrumentation",
        "providerHost": "batcave.biz",
        "extensionPackageName": "eu.kanade.tachiyomi.extension.en.batcave",
        "extensionInstallSucceeded": True,
        "extensionLoadSucceeded": True,
        "sourceName": "BatCave",
        "sourceRequestSucceeded": True,
        "sourceResultCount": 8,
        "dleGuardTrustCookieObserved": True,
        "webView": {
            "available": True,
            "packageName": "com.google.android.webview",
            "versionName": "142.0.0",
        },
        "error": None,
    }


class BatCaveAndroidWebViewEvidenceTests(unittest.TestCase):
    def test_positive_probe_unblocks_only_exact_runtime_proof(self) -> None:
        result = bind(
            runtime_report(),
            android_probe(),
            base=BASE,
            candidate=CANDIDATE,
            miyorare_revision=MIYORARE,
        )
        proof = result["proofs"][0]
        self.assertFalse(proof["infrastructureBlocked"])
        self.assertTrue(proof["androidWebViewExecutionProven"])
        self.assertEqual(12345, proof["androidWebViewEvidence"]["workflowRunId"])
        self.assertIn(":android-webview", proof["evidenceId"])

    def test_missing_dle_guard_cookie_stays_fail_closed(self) -> None:
        probe = android_probe()
        probe["dleGuardTrustCookieObserved"] = False
        result = bind(
            runtime_report(),
            probe,
            base=BASE,
            candidate=CANDIDATE,
            miyorare_revision=MIYORARE,
        )
        proof = result["proofs"][0]
        self.assertTrue(proof["infrastructureBlocked"])
        self.assertFalse(proof["androidWebViewExecutionProven"])
        self.assertNotIn(":android-webview", proof["evidenceId"])

    def test_missing_workflow_run_id_stays_fail_closed(self) -> None:
        probe = android_probe()
        probe["workflowRunId"] = None
        result = bind(
            runtime_report(),
            probe,
            base=BASE,
            candidate=CANDIDATE,
            miyorare_revision=MIYORARE,
        )
        proof = result["proofs"][0]
        self.assertTrue(proof["infrastructureBlocked"])
        self.assertFalse(proof["androidWebViewExecutionProven"])

    def test_candidate_or_host_mismatch_is_rejected(self) -> None:
        probe = android_probe()
        probe["candidateRevision"] = "a" * 40
        with self.assertRaises(ValueError):
            bind(
                runtime_report(),
                probe,
                base=BASE,
                candidate=CANDIDATE,
                miyorare_revision=MIYORARE,
            )

        probe = android_probe()
        probe["miyorareRevision"] = "b" * 40
        with self.assertRaises(ValueError):
            bind(
                runtime_report(),
                probe,
                base=BASE,
                candidate=CANDIDATE,
                miyorare_revision=MIYORARE,
            )

    def test_failed_build_proof_cannot_be_upgraded_by_android_probe(self) -> None:
        report = runtime_report()
        report["proofs"][0]["result"] = "FAIL"
        result = bind(
            report,
            android_probe(),
            base=BASE,
            candidate=CANDIDATE,
            miyorare_revision=MIYORARE,
        )
        proof = result["proofs"][0]
        self.assertTrue(proof["infrastructureBlocked"])
        self.assertFalse(proof["androidWebViewExecutionProven"])

    def test_probe_binding_does_not_mutate_input(self) -> None:
        report = runtime_report()
        before = copy.deepcopy(report)
        bind(report, android_probe(), base=BASE, candidate=CANDIDATE, miyorare_revision=MIYORARE)
        self.assertEqual(before, report)

    def test_android_harness_uses_real_miyorare_extension_and_webview_path(self) -> None:
        harness = (ROOT / "compatibility/android-harness/KeiyoushiBatCaveAndroidWebViewProbeTest.kt").read_text(encoding="utf-8")
        self.assertIn("MihonExtensionLoader.installPrivateExtensionFile", harness)
        self.assertIn("loadExtensions(context, privateMode = true)", harness)
        self.assertIn("source.getPopularManga(1)", harness)
        self.assertIn("CookieManager.getInstance()", harness)
        self.assertIn("WebView.getCurrentWebViewPackage()", harness)
        self.assertIn('"__guard_trust=; Max-Age=0; Path=/"', harness)
        self.assertIn("trustCookieValue.isNotBlank()", harness)
        self.assertNotIn('.put("dleGuardTrustCookieObserved", true)', harness)

    def test_workflow_is_read_only_exact_and_fail_closed(self) -> None:
        workflow = (ROOT / ".github/workflows/batcave-android-webview-evidence.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertIn(BASE, workflow)
        self.assertIn(CANDIDATE, workflow)
        self.assertIn(MIYORARE, workflow)
        self.assertIn("connectedDebugAndroidTest", workflow)
        self.assertIn("bind_batcave_android_webview_evidence.py", workflow)
        self.assertIn("p2-batcave-evidence.json", workflow)
        self.assertIn("platforms;android-37.0", workflow)
        self.assertIn("system-images;android-35;google_apis;x86_64", workflow)
        self.assertIn("if: always() && steps.android_probe.outcome != 'skipped'", workflow)
        self.assertNotIn("android sdk install --canary", workflow)
        self.assertNotIn("compatibility-farm-foundation", workflow)
        self.assertNotIn("gh pr merge", workflow)
        self.assertNotIn("git push", workflow)


if __name__ == "__main__":
    unittest.main()
