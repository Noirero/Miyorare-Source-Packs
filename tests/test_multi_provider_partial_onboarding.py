#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WORKER_SPEC = importlib.util.spec_from_file_location(
    "source_pending_worker_partial", ROOT / "tools" / "source_pending_worker.py"
)
assert WORKER_SPEC and WORKER_SPEC.loader
worker = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(worker)

APPROVAL_SPEC = importlib.util.spec_from_file_location(
    "source_pending_approval_partial", ROOT / "tools" / "source_pending_approval.py"
)
assert APPROVAL_SPEC and APPROVAL_SPEC.loader
approval = importlib.util.module_from_spec(APPROVAL_SPEC)
APPROVAL_SPEC.loader.exec_module(approval)

OLD_KEI = "a" * 40
KEI = "b" * 40
GEK = "c" * 40
UMA = "d" * 40
CANONICAL = "miyorare:inventory-id:MIKOROKU"


def mikoroku_source() -> dict:
    return {
        "canonicalId": CANONICAL,
        "displayName": "MikoRoku",
        "language": "id",
        "providers": ["gekkoushi", "keiyoushi"],
        "upstreamIdentities": {
            "gekkoushi": {
                "sourceName": "MIKOROKU",
                "file": "src/Mikoroku.kt",
            },
            "keiyoushi": {
                "sourceName": "MikoRoku",
                "module": "src/id/mikoroku",
            },
        },
        "currentVersion": {"gekkoushi": GEK, "keiyoushi": OLD_KEI},
        "lastKnownGood": {"gekkoushi": GEK, "keiyoushi": OLD_KEI},
        "healthyHistory": [],
        "authType": "UNSUPPORTED",
        "adapterFamily": "unclassified",
        "runtimeHealth": "UNKNOWN",
        "ownerActionRequired": False,
        "publishEligible": False,
        "selectionReasons": ["automatic-source-inventory"],
        "compatibilityEnrollment": {
            "state": "PENDING",
            "parserCoverageRequired": False,
        },
    }


def registry() -> dict:
    return {
        "schemaVersion": 1,
        "providerBaselines": {
            "gekkoushi": GEK,
            "keiyoushi": KEI,
            "uma": UMA,
        },
        "sources": [mikoroku_source()],
    }


class MultiProviderPartialOnboardingTest(unittest.TestCase):
    def test_stale_held_source_is_requeued_after_provider_baseline_moves(self) -> None:
        state = worker.normalize_state({
            "schemaVersion": 2,
            "sources": {
                CANONICAL: {
                    "schemaVersion": 2,
                    "state": worker.HELD,
                    "attempts": 1,
                    "approvalState": "NOT_READY",
                    "testedVersions": {
                        "gekkoushi": GEK,
                        "keiyoushi": OLD_KEI,
                    },
                }
            },
        })

        plan = worker.build_plan(registry(), state, 8)

        self.assertEqual(plan["invalidatedHeld"], 1)
        self.assertEqual(state["sources"][CANONICAL]["state"], worker.RETRY)
        self.assertEqual(plan["items"][0]["canonicalId"], CANONICAL)

    def test_mikoroku_can_activate_keiyoushi_while_gekkoushi_remains_held(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gekkoushi = root / "gekkoushi"
            keiyoushi = root / "keiyoushi"
            uma = root / "uma"

            (gekkoushi / "src").mkdir(parents=True)
            (gekkoushi / "src/Mikoroku.kt").write_text(
                '@Broken("Domain has no DNS records — site is gone")\n'
                'MangaParser(context, MangaParserSource.MIKOROKU, "www.mikoroku.web.id")',
                encoding="utf-8",
            )
            module = keiyoushi / "src/id/mikoroku"
            module.mkdir(parents=True)
            (module / "MikoRoku.kt").write_text(
                'class MikoRoku { val baseUrl = "https://mikoroku.com" }',
                encoding="utf-8",
            )
            (module / "build.gradle.kts").write_text(
                'val baseUrl = "https://mikoroku.com"',
                encoding="utf-8",
            )

            plan = {
                "items": [{
                    "canonicalId": CANONICAL,
                    "language": "id",
                    "providers": ["gekkoushi", "keiyoushi"],
                    "upstreamIdentities": mikoroku_source()["upstreamIdentities"],
                    "attempts": 1,
                }],
            }
            original_probe = worker.http_probe
            worker.http_probe = lambda host, timeout: {
                "reachable": host == "mikoroku.com",
                "httpStatus": 200,
                "url": f"https://{host}/",
            }
            try:
                profile = worker.assess_plan(
                    plan,
                    {
                        "gekkoushi": gekkoushi,
                        "keiyoushi": keiyoushi,
                        "uma": uma,
                    },
                    {
                        "gekkoushi": {"*": True},
                        "keiyoushi": {"src/id/mikoroku": True},
                        "uma": {},
                    },
                    1.0,
                    3,
                )
            finally:
                worker.http_probe = original_probe

        profiled = profile["results"][0]
        self.assertEqual(profiled["state"], worker.PROFILE)
        self.assertEqual(profiled["selectedProviders"], ["keiyoushi"])
        memberships = {
            item["provider"]: item
            for item in profiled["evidence"]["profile"]["memberships"]
        }
        self.assertFalse(memberships["gekkoushi"]["profilePass"])
        self.assertTrue(memberships["keiyoushi"]["profilePass"])

        finalized = worker.finalize_results(
            profile,
            {
                "executionMode": "real-live-parser",
                "results": [{
                    "canonicalId": CANONICAL,
                    "provider": "keiyoushi",
                    "status": "PASS",
                    "parserExecution": True,
                    "detailsTraversal": True,
                    "chapterTraversal": True,
                    "pageExtraction": True,
                }],
            },
            3,
        )
        result = finalized["results"][0]
        self.assertEqual(result["state"], worker.READY)
        self.assertEqual(result["selectedProviders"], ["keiyoushi"])

        state, _ = worker.apply_results(
            registry(),
            worker.normalize_state({}),
            finalized,
            "123",
            "2026-10-18T00:00:00Z",
        )
        entry = state["sources"][CANONICAL]
        self.assertEqual(entry["testedVersions"], {"keiyoushi": KEI})
        self.assertEqual(entry["selectedProviders"], ["keiyoushi"])

        reg = registry()
        approval_plan = approval.plan(reg, state)
        item = approval_plan["sources"][0]
        self.assertEqual(item["providers"], ["keiyoushi"])
        self.assertEqual(item["heldProviders"][0]["provider"], "gekkoushi")
        self.assertIn("Domain has no DNS records", item["heldProviders"][0]["reason"])

        updated_reg, updated_state, receipt = approval.apply(
            reg,
            state,
            approval_plan,
            "Noirero:149634319",
            "2026-10-18T00:00:01Z",
            "456",
        )
        source = updated_reg["sources"][0]
        self.assertEqual(source["providers"], ["keiyoushi"])
        self.assertEqual(set(source["upstreamIdentities"]), {"keiyoushi"})
        self.assertEqual(source["currentVersion"], {"keiyoushi": KEI})
        self.assertEqual(source["lastKnownGood"], {"keiyoushi": KEI})
        self.assertEqual(source["onboardingApproval"]["activeProviders"], ["keiyoushi"])
        self.assertEqual(source["onboardingApproval"]["heldProviders"][0]["provider"], "gekkoushi")
        self.assertEqual(updated_state["sources"][CANONICAL]["state"], approval.APPROVED)
        self.assertEqual(receipt["count"], 1)


if __name__ == "__main__":
    unittest.main()
