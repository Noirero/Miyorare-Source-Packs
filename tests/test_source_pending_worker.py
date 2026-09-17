#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_pending_worker", ROOT / "tools" / "source_pending_worker.py"
)
assert SPEC and SPEC.loader
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


def source(canonical_id: str, language: str, *, state: str = "PENDING") -> dict:
    return {
        "canonicalId": canonical_id,
        "language": language,
        "contentProfile": "manga",
        "authType": "UNSUPPORTED",
        "adapterFamily": "unclassified",
        "providers": ["uma"],
        "upstreamIdentities": {
            "uma": {"sourceName": canonical_id, "file": f"src/{canonical_id}.kt"}
        },
        "compatibilityEnrollment": {
            "state": state,
            "parserCoverageRequired": state == "ACTIVE",
        },
        "updateState": "CANDIDATE",
        "runtimeHealth": "UNKNOWN",
        "approvalState": "NOT_READY",
        "ownerActionRequired": False,
        "publishEligible": False,
    }


class PendingWorkerTest(unittest.TestCase):
    def test_plan_balances_languages_and_skips_active(self) -> None:
        registry = {
            "sources": [
                source("id-a", "id"),
                source("id-b", "id"),
                source("en-a", "en"),
                source("active", "en", state="ACTIVE"),
            ]
        }
        plan = worker.build_plan(registry, 2)
        self.assertEqual(plan["batchSize"], 2)
        self.assertEqual({item["language"] for item in plan["items"]}, {"id", "en"})
        self.assertNotIn("active", {item["canonicalId"] for item in plan["items"]})

    def test_assess_passes_compiled_reachable_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uma = root / "uma"
            (uma / "src").mkdir(parents=True)
            (uma / "src" / "alpha.kt").write_text(
                'class Alpha : Madara() { val baseUrl = "https://example.com" }',
                encoding="utf-8",
            )
            plan = {
                "items": [
                    {
                        "canonicalId": "alpha",
                        "language": "en",
                        "providers": ["uma"],
                        "upstreamIdentities": {
                            "uma": {"sourceName": "Alpha", "file": "src/alpha.kt"}
                        },
                        "attempts": 0,
                    }
                ]
            }
            original_probe = worker.http_probe
            worker.http_probe = lambda host, timeout: {
                "reachable": True,
                "httpStatus": 200,
                "url": f"https://{host}/",
            }
            try:
                result = worker.assess_plan(
                    plan,
                    {"uma": uma, "keiyoushi": root, "gekkoushi": root},
                    {"uma": {"*": True}},
                    1.0,
                    3,
                )
            finally:
                worker.http_probe = original_probe

        item = result["results"][0]
        self.assertEqual(item["state"], worker.READY)
        self.assertEqual(item["adapterFamily"], "madara")
        self.assertEqual(item["evidence"]["gate"], "PASS")

    def test_failure_retries_then_holds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uma = root / "uma"
            (uma / "src").mkdir(parents=True)
            (uma / "src" / "alpha.kt").write_text(
                'val baseUrl = "https://example.com"', encoding="utf-8"
            )
            original_probe = worker.http_probe
            worker.http_probe = lambda host, timeout: {"reachable": False, "detail": "timeout"}
            try:
                base = {
                    "canonicalId": "alpha",
                    "language": "en",
                    "providers": ["uma"],
                    "upstreamIdentities": {
                        "uma": {"sourceName": "Alpha", "file": "src/alpha.kt"}
                    },
                }
                retry = worker.assess_plan(
                    {"items": [{**base, "attempts": 0}]},
                    {"uma": uma, "keiyoushi": root, "gekkoushi": root},
                    {"uma": {"*": True}},
                    1.0,
                    3,
                )
                held = worker.assess_plan(
                    {"items": [{**base, "attempts": 2}]},
                    {"uma": uma, "keiyoushi": root, "gekkoushi": root},
                    {"uma": {"*": True}},
                    1.0,
                    3,
                )
            finally:
                worker.http_probe = original_probe

        self.assertEqual(retry["results"][0]["state"], worker.RETRY)
        self.assertEqual(held["results"][0]["state"], worker.HELD)

    def test_apply_marks_ready_without_activating(self) -> None:
        registry = {"sources": [source("alpha", "en")]}
        results = {
            "results": [
                {
                    "canonicalId": "alpha",
                    "state": worker.READY,
                    "attempts": 1,
                    "adapterFamily": "madara",
                    "authType": "NO_AUTH",
                    "evidence": {"gate": "PASS", "memberships": []},
                    "evidenceSha256": "abc",
                }
            ]
        }
        worker.apply_results(registry, results, "123", "2026-09-18T00:00:00Z")
        item = registry["sources"][0]
        self.assertEqual(item["approvalState"], "WAITING_FOR_APPROVAL")
        self.assertEqual(item["runtimeHealth"], "HEALTHY")
        self.assertEqual(item["compatibilityEnrollment"]["state"], "PENDING")
        self.assertFalse(item["publishEligible"])
        self.assertFalse(item["ownerActionRequired"])

    def test_ready_and_held_are_not_requeued(self) -> None:
        ready = source("ready", "id")
        ready["approvalState"] = "WAITING_FOR_APPROVAL"
        ready["onboarding"] = {"state": worker.READY}
        held = source("held", "en")
        held["onboarding"] = {"state": worker.HELD}
        pending = source("pending", "en")
        plan = worker.build_plan({"sources": [ready, held, pending]}, 8)
        self.assertEqual([item["canonicalId"] for item in plan["items"]], ["pending"])


if __name__ == "__main__":
    unittest.main()
