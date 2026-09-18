#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_pending_worker", ROOT / "tools" / "source_pending_worker.py")
assert SPEC and SPEC.loader
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


def source(canonical_id: str, language: str, *, state: str = "PENDING") -> dict:
    return {
        "canonicalId": canonical_id,
        "language": language,
        "providers": ["uma"],
        "upstreamIdentities": {"uma": {"sourceName": canonical_id, "file": f"src/{canonical_id}.kt"}},
        "currentVersion": {"uma": "a" * 40},
        "lastKnownGood": {"uma": "a" * 40},
        "compatibilityEnrollment": {"state": state, "parserCoverageRequired": state == "ACTIVE"},
    }


def profiled() -> dict:
    evidence = {
        "profile": {
            "gate": "PASS",
            "memberships": [
                {
                    "provider": "uma",
                    "locator": "src/alpha.kt",
                    "profilePass": True,
                    "compile": True,
                    "probe": {"reachable": True},
                }
            ],
        },
        "attempts": 1,
    }
    return {
        "canonicalId": "alpha",
        "state": worker.PROFILE,
        "attempts": 1,
        "adapterFamily": "madara",
        "authType": "NO_AUTH",
        "evidence": evidence,
        "evidenceSha256": worker.evidence_digest(evidence),
    }


class PendingWorkerTest(unittest.TestCase):
    def test_legacy_v1_state_is_requeued_for_real_parser_v2(self) -> None:
        legacy = {
            "schemaVersion": 1,
            "sources": {
                "old-ready": {"state": worker.READY, "attempts": 1},
                "old-held": {"state": worker.HELD, "attempts": 3},
            },
        }
        migrated = worker.normalize_state(legacy)
        self.assertEqual(migrated["schemaVersion"], 2)
        self.assertEqual(migrated["sources"], {})

        registry = {
            "sources": [
                source("old-ready", "id"),
                source("old-held", "en"),
            ]
        }
        plan = worker.build_plan(registry, migrated, 8)
        self.assertEqual(
            {item["canonicalId"] for item in plan["items"]},
            {"old-ready", "old-held"},
        )

    def test_plan_balances_languages_and_skips_active(self) -> None:
        registry = {"sources": [source("id-a", "id"), source("id-b", "id"), source("en-a", "en"), source("active", "en", state="ACTIVE")]}
        plan = worker.build_plan(registry, worker.normalize_state({}), 2)
        self.assertEqual(plan["batchSize"], 2)
        self.assertEqual({item["language"] for item in plan["items"]}, {"id", "en"})
        self.assertNotIn("active", {item["canonicalId"] for item in plan["items"]})

    def test_plan_reserves_retry_capacity_without_starving_fresh_sources(self) -> None:
        sources = [
            source("retry-id", "id"),
            source("retry-en", "en"),
            source("fresh-id-a", "id"),
            source("fresh-en-a", "en"),
            source("fresh-id-b", "id"),
            source("fresh-en-b", "en"),
            source("fresh-id-c", "id"),
            source("fresh-en-c", "en"),
            source("fresh-id-d", "id"),
            source("fresh-en-d", "en"),
        ]
        state = worker.normalize_state({
            "schemaVersion": 2,
            "sources": {
                "retry-id": {"state": worker.RETRY, "attempts": 1, "lastCheckedAt": "2026-09-18T00:00:00Z"},
                "retry-en": {"state": worker.RETRY, "attempts": 1, "lastCheckedAt": "2026-09-18T00:01:00Z"},
            },
        })
        plan = worker.build_plan({"sources": sources}, state, 8)
        ids = {item["canonicalId"] for item in plan["items"]}
        self.assertEqual(plan["batchSize"], 8)
        self.assertEqual(plan["retrySlots"], 2)
        self.assertIn("retry-id", ids)
        self.assertIn("retry-en", ids)
        self.assertTrue(any(item["canonicalId"].startswith("fresh-") for item in plan["items"]))

    def test_infer_host_understands_domain_config_and_parser_constructor(self) -> None:
        self.assertEqual(
            worker.infer_host('private val baseUrl = "https://$domain"\noverride val configKeyDomain = ConfigKey.Domain("alawale.net")'),
            "alawale.net",
        )
        self.assertEqual(
            worker.infer_host('MadaraParser(context, MangaParserSource.X, "reader.example.com", 10)'),
            "reader.example.com",
        )
        self.assertEqual(
            worker.infer_host('@MangaSourceParser("X", "Display.example", "en")\nManga18Parser(context, MangaParserSource.X, "real.example.org")'),
            "real.example.org",
        )

    def test_upstream_broken_marker_holds_without_wasting_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gek = root / "gekkoushi"
            source_file = gek / "src/broken.kt"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                '@Broken("Original site closed")\nMadaraParser(context, MangaParserSource.X, "closed.example.com")',
                encoding="utf-8",
            )
            plan = {"items": [{
                "canonicalId": "broken",
                "language": "en",
                "providers": ["gekkoushi"],
                "upstreamIdentities": {"gekkoushi": {"file": "src/broken.kt"}},
                "attempts": 0,
            }]}
            result = worker.assess_plan(
                plan,
                {"gekkoushi": gek, "uma": root, "keiyoushi": root},
                {"gekkoushi": {"*": True}},
                1.0,
                3,
            )
        row = result["results"][0]
        self.assertEqual(row["state"], worker.HELD)
        member = row["evidence"]["profile"]["memberships"][0]
        self.assertEqual(member["upstreamBrokenReason"], "Original site closed")
        self.assertEqual(member["probe"]["detail"], "upstream-declared-broken")

    def test_compile_and_reachability_only_reach_parser_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uma = root / "uma"
            (uma / "src").mkdir(parents=True)
            (uma / "src" / "alpha.kt").write_text('class Alpha : Madara() { val baseUrl = "https://example.com" }', encoding="utf-8")
            plan = {"items": [{"canonicalId": "alpha", "language": "en", "providers": ["uma"], "upstreamIdentities": {"uma": {"sourceName": "Alpha", "file": "src/alpha.kt"}}, "attempts": 0}]}
            original_probe = worker.http_probe
            worker.http_probe = lambda host, timeout: {"reachable": True, "httpStatus": 200, "url": f"https://{host}/"}
            try:
                result = worker.assess_plan(plan, {"uma": uma, "keiyoushi": root, "gekkoushi": root}, {"uma": {"*": True}}, 1.0, 3)
            finally:
                worker.http_probe = original_probe
        item = result["results"][0]
        self.assertEqual(item["state"], worker.PROFILE)
        self.assertEqual(item["adapterFamily"], "madara")
        self.assertEqual(item["evidence"]["profile"]["gate"], "PASS")

    def test_real_parser_pass_is_required_for_ready(self) -> None:
        profile_results = {"results": [profiled()]}
        parser_pass = {
            "executionMode": "real-live-parser",
            "results": [{
                "canonicalId": "alpha",
                "provider": "uma",
                "status": "PASS",
                "parserExecution": True,
                "detailsTraversal": True,
                "chapterTraversal": True,
                "pageExtraction": True,
            }],
        }
        final = worker.finalize_results(profile_results, parser_pass, 3)["results"][0]
        self.assertEqual(final["state"], worker.READY)
        self.assertEqual(final["evidence"]["gate"], "REAL_PARSER_PASS")

        missing = worker.finalize_results(profile_results, {"results": []}, 3)["results"][0]
        self.assertEqual(missing["state"], worker.RETRY)
        self.assertEqual(missing["evidence"]["gate"], "REAL_PARSER_BLOCKED")

    def test_infrastructure_parser_failure_does_not_consume_source_retry(self) -> None:
        row = profiled()
        row["attempts"] = 3
        row["evidence"]["attempts"] = 3
        parser_fail = {
            "results": [{
                "canonicalId": "alpha",
                "provider": "uma",
                "status": "FAIL",
                "parserExecution": True,
                "detailsTraversal": False,
                "chapterTraversal": False,
                "pageExtraction": False,
                "failureType": "java.lang.NoClassDefFoundError",
                "failureMessage": "missing runtime class",
            }]
        }
        final = worker.finalize_results({"results": [row]}, parser_fail, 3)["results"][0]
        self.assertEqual(final["state"], worker.RETRY)
        self.assertEqual(final["attempts"], 2)
        self.assertTrue(final["evidence"]["diagnosis"]["automationInfrastructureOnly"])
        self.assertFalse(final["evidence"]["diagnosis"]["attemptConsumed"])

    def test_real_source_failure_still_consumes_retry(self) -> None:
        row = profiled()
        row["attempts"] = 3
        row["evidence"]["attempts"] = 3
        parser_fail = {
            "results": [{
                "canonicalId": "alpha",
                "provider": "uma",
                "status": "FAIL",
                "parserExecution": True,
                "detailsTraversal": False,
                "chapterTraversal": False,
                "pageExtraction": False,
                "failureType": "org.opentest4j.AssertionFailedError",
                "failureMessage": "live browse returned no manga; lastFailure=HttpStatusException",
            }]
        }
        final = worker.finalize_results({"results": [row]}, parser_fail, 3)["results"][0]
        self.assertEqual(final["state"], worker.HELD)
        self.assertEqual(
            final["evidence"]["diagnosis"]["categories"][0]["category"],
            "HTTP_BLOCKED_OR_UPSTREAM_FAILURE",
        )

    def test_auth_required_parser_failure_holds_immediately(self) -> None:
        row = profiled()
        row["authType"] = "FORM"
        parser_fail = {
            "results": [{
                "canonicalId": "alpha",
                "provider": "uma",
                "status": "FAIL",
                "parserExecution": False,
                "reason": "AUTH_REQUIRED:FORM",
            }]
        }
        final = worker.finalize_results({"results": [row]}, parser_fail, 3)["results"][0]
        self.assertEqual(final["state"], worker.HELD)
        self.assertEqual(final["attempts"], 1)

    def test_real_parser_failure_holds_at_threshold(self) -> None:
        row = profiled()
        row["attempts"] = 3
        row["evidence"]["attempts"] = 3
        parser_fail = {
            "results": [{
                "canonicalId": "alpha",
                "provider": "uma",
                "status": "FAIL",
                "parserExecution": True,
                "detailsTraversal": False,
                "chapterTraversal": False,
                "pageExtraction": False,
            }]
        }
        final = worker.finalize_results({"results": [row]}, parser_fail, 3)["results"][0]
        self.assertEqual(final["state"], worker.HELD)

    def test_failure_retries_then_holds_before_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uma = root / "uma"
            (uma / "src").mkdir(parents=True)
            (uma / "src" / "alpha.kt").write_text('val baseUrl = "https://example.com"', encoding="utf-8")
            original_probe = worker.http_probe
            worker.http_probe = lambda host, timeout: {"reachable": False, "detail": "timeout"}
            try:
                base = {"canonicalId": "alpha", "language": "en", "providers": ["uma"], "upstreamIdentities": {"uma": {"sourceName": "Alpha", "file": "src/alpha.kt"}}}
                retry = worker.assess_plan({"items": [{**base, "attempts": 0}]}, {"uma": uma, "keiyoushi": root, "gekkoushi": root}, {"uma": {"*": True}}, 1.0, 3)
                held = worker.assess_plan({"items": [{**base, "attempts": 2}]}, {"uma": uma, "keiyoushi": root, "gekkoushi": root}, {"uma": {"*": True}}, 1.0, 3)
            finally:
                worker.http_probe = original_probe
        self.assertEqual(retry["results"][0]["state"], worker.RETRY)
        self.assertEqual(held["results"][0]["state"], worker.HELD)

    def test_apply_updates_state_without_mutating_registry(self) -> None:
        registry = {"sources": [source("alpha", "en")]}
        before = repr(registry)
        result = profiled()
        result["state"] = worker.READY
        state, summary = worker.apply_results(registry, worker.normalize_state({}), {"results": [result]}, "123", "2026-09-18T00:00:00Z")
        self.assertEqual(repr(registry), before)
        self.assertEqual(state["sources"]["alpha"]["approvalState"], "WAITING_FOR_APPROVAL")
        self.assertEqual(
            state["sources"]["alpha"]["testedVersions"],
            {"uma": registry["sources"][0]["currentVersion"]["uma"]},
        )
        self.assertFalse(state["sources"]["alpha"]["publishEligible"])
        self.assertFalse(state["sources"]["alpha"]["ownerActionRequired"])
        self.assertEqual(summary["states"][worker.READY], 1)

    def test_ready_and_held_are_not_requeued(self) -> None:
        registry = {"sources": [source("ready", "id"), source("held", "en"), source("pending", "en")]}
        state = worker.normalize_state({"schemaVersion": 2, "sources": {"ready": {"state": worker.READY}, "held": {"state": worker.HELD}}})
        plan = worker.build_plan(registry, state, 8)
        self.assertEqual([item["canonicalId"] for item in plan["items"]], ["pending"])


if __name__ == "__main__":
    unittest.main()
