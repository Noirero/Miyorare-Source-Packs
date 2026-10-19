from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_parser_coverage_backfill", ROOT / "tools" / "source_parser_coverage_backfill.py"
)
assert SPEC and SPEC.loader
backfill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backfill)


def approved_source(
    canonical_id: str,
    provider: str,
    adapter_family: str,
    tested_sha: str,
    *,
    module: str | None = None,
) -> dict:
    identity = {"module": module} if module else {"file": "src/main/kotlin/example/Example.kt"}
    return {
        "canonicalId": canonical_id,
        "adapterFamily": adapter_family,
        "providers": [provider],
        "currentVersion": {provider: tested_sha},
        "upstreamIdentities": {provider: identity},
        "compatibilityEnrollment": {"state": "ACTIVE", "parserCoverageRequired": True},
        "onboardingApproval": {"state": "APPROVED"},
    }


def approved_worker(
    canonical_id: str,
    provider: str,
    tested_sha: str,
    test_class: str,
    *,
    fqcn: str | None = None,
) -> dict:
    parser_membership = {
        "canonicalId": canonical_id,
        "provider": provider,
        "status": "PASS",
        "parserExecution": True,
        "detailsTraversal": True,
        "chapterTraversal": True,
        "pageExtraction": True,
        "testClass": test_class,
    }
    if fqcn:
        parser_membership["fqcn"] = fqcn
    return {
        "state": "APPROVED",
        "approvalState": "APPROVED",
        "testedVersions": {provider: tested_sha},
        "evidence": {
            "profile": {
                "gate": "PASS",
                "memberships": [{"provider": provider, "profilePass": True}],
            },
            "parser": {
                "gate": "PASS",
                "memberships": [parser_membership],
            },
        },
    }


class ParserCoverageBackfillTest(unittest.TestCase):
    def test_backfills_proven_tsuki_membership_and_live_harness(self) -> None:
        sha = "1" * 40
        canonical = "miyorare:inventory-en:EXAMPLE"
        registry = {
            "sources": [approved_source(canonical, "gekkoushi", "gekkoushi-native", sha)]
        }
        state = {
            "sources": {
                canonical: approved_worker(
                    canonical,
                    "gekkoushi",
                    sha,
                    "compatibilityfarm.AutoLive_gekkoushi_deadbeef0001",
                    fqcn="tsuki.site.example.Example",
                )
            }
        }
        families = {"families": []}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = backfill.backfill(registry, state, families, root, expected_missing_count=1)

            self.assertEqual(report["addedMembershipCount"], 1)
            self.assertEqual(report["remainingMissingCount"], 0)
            self.assertFalse(report["mutatesRegistry"])
            self.assertEqual(len(families["families"]), 1)
            family = families["families"][0]
            self.assertEqual(family["provider"], "gekkoushi")
            self.assertEqual(family["registryAdapterFamily"], "gekkoushi-native")
            self.assertEqual(family["members"][0]["canonicalId"], canonical)

            harness = root / "gekkoushi" / "AutoLive_gekkoushi_deadbeef0001.kt"
            context = root / "gekkoushi" / "LiveMangaLoaderContext.kt"
            self.assertTrue(harness.is_file())
            self.assertTrue(context.is_file())
            self.assertIn("tsuki.site.example.Example", harness.read_text(encoding="utf-8"))

    def test_backfills_proven_keiyoushi_membership(self) -> None:
        sha = "2" * 40
        canonical = "miyorare:inventory-en:COLORIZED"
        registry = {
            "sources": [
                approved_source(
                    canonical,
                    "keiyoushi",
                    "custom-paged-html",
                    sha,
                    module="src/en/colorized",
                )
            ]
        }
        state = {
            "sources": {
                canonical: approved_worker(
                    canonical,
                    "keiyoushi",
                    sha,
                    "compatibilityfarm.AutoLive_keiyoushi_deadbeef0002",
                )
            }
        }
        families = {"families": []}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = backfill.backfill(registry, state, families, root, expected_missing_count=1)
            self.assertEqual(report["addedMembershipCount"], 1)
            member = families["families"][0]["members"][0]
            self.assertEqual(member["module"], "src/en/colorized")
            harness = root / "keiyoushi" / "AutoLive_keiyoushi_deadbeef0002.kt"
            self.assertTrue(harness.is_file())
            self.assertIn("KeiSource", harness.read_text(encoding="utf-8"))

    def test_refuses_non_passing_parser_evidence(self) -> None:
        sha = "3" * 40
        canonical = "miyorare:inventory-en:BROKEN"
        registry = {
            "sources": [approved_source(canonical, "uma", "uma-native", sha)]
        }
        worker = approved_worker(
            canonical,
            "uma",
            sha,
            "compatibilityfarm.AutoLive_uma_deadbeef0003",
            fqcn="tsuki.site.example.Broken",
        )
        worker["evidence"]["parser"]["memberships"][0]["pageExtraction"] = False
        state = {"sources": {canonical: worker}}
        families = {"families": []}

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(backfill.CoverageBackfillError):
                backfill.backfill(registry, state, families, Path(tmp), expected_missing_count=1)

    def test_is_idempotent_when_membership_already_declared(self) -> None:
        sha = "4" * 40
        canonical = "miyorare:inventory-en:EXISTING"
        source = approved_source(canonical, "uma", "uma-native", sha)
        registry = {"sources": [source]}
        state = {
            "sources": {
                canonical: approved_worker(
                    canonical,
                    "uma",
                    sha,
                    "compatibilityfarm.AutoLive_uma_deadbeef0004",
                    fqcn="tsuki.site.example.Existing",
                )
            }
        }
        families = {
            "families": [
                {
                    "id": "existing",
                    "provider": "uma",
                    "members": [
                        {
                            "canonicalId": canonical,
                            "testClass": "compatibilityfarm.ExistingHarness",
                        }
                    ],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            report = backfill.backfill(registry, state, families, Path(tmp), expected_missing_count=0)
            self.assertEqual(report["addedMembershipCount"], 0)
            self.assertEqual(len(families["families"]), 1)


if __name__ == "__main__":
    unittest.main()
