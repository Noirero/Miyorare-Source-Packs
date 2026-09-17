#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_live_parser_harness", ROOT / "tools" / "source_live_parser_harness.py"
)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


class LiveParserHarnessTest(unittest.TestCase):
    def test_generate_tsuki_harness_for_profiled_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src/main/kotlin/tsuki/site/en/Alpha.kt"
            source.parent.mkdir(parents=True)
            source.write_text(
                '''package tsuki.site.en\nimport tsuki.MangaLoaderContext\ninternal class Alpha(context: MangaLoaderContext) : Base(context)\n''',
                encoding="utf-8",
            )
            plan = {"items": [{
                "canonicalId": "alpha",
                "providers": ["uma"],
                "upstreamIdentities": {"uma": {"file": "src/main/kotlin/tsuki/site/en/Alpha.kt"}},
            }]}
            profiles = {"results": [{
                "canonicalId": "alpha",
                "state": harness.PROFILE_READY,
                "authType": "NO_AUTH",
            }]}
            manifest = harness.generate(plan, profiles, "uma", root)
            self.assertEqual(len(manifest["tests"]), 1)
            self.assertEqual(manifest["tests"][0]["fqcn"], "tsuki.site.en.Alpha")
            test_class = manifest["tests"][0]["testClass"].split(".")[-1]
            self.assertTrue((root / f"src/test/kotlin/compatibilityfarm/{test_class}.kt").is_file())
            self.assertTrue((root / "src/test/kotlin/compatibilityfarm/LiveMangaLoaderContext.kt").is_file())

    def test_auth_source_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = {"items": [{
                "canonicalId": "secure",
                "providers": ["uma"],
                "upstreamIdentities": {"uma": {"file": "src/Secure.kt"}},
            }]}
            profiles = {"results": [{
                "canonicalId": "secure",
                "state": harness.PROFILE_READY,
                "authType": "TOKEN",
            }]}
            manifest = harness.generate(plan, profiles, "uma", root)
            self.assertEqual(manifest["tests"], [])
            self.assertEqual(manifest["blocked"][0]["reason"], "AUTH_REQUIRED:TOKEN")

    def test_collect_missing_junit_is_failure(self) -> None:
        manifest = {
            "provider": "uma",
            "tests": [{
                "canonicalId": "alpha",
                "provider": "uma",
                "testClass": "compatibilityfarm.AutoLive_uma_x",
                "resultsDir": "/does/not/exist",
            }],
            "blocked": [],
        }
        report = harness.collect([manifest])
        self.assertEqual(report["results"][0]["status"], "FAIL")
        self.assertFalse(report["results"][0]["parserExecution"])

    def test_keiyoushi_generation_targets_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = root / "src/en/example"
            module.mkdir(parents=True)
            plan = {"items": [{
                "canonicalId": "kei",
                "providers": ["keiyoushi"],
                "upstreamIdentities": {"keiyoushi": {"module": "src/en/example"}},
            }]}
            profiles = {"results": [{
                "canonicalId": "kei",
                "state": harness.PROFILE_READY,
                "authType": "NO_AUTH",
            }]}
            manifest = harness.generate(plan, profiles, "keiyoushi", root)
            self.assertEqual(len(manifest["tests"]), 1)
            test_class = manifest["tests"][0]["testClass"].split(".")[-1]
            self.assertTrue((module / f"compatibility-farm-test/{test_class}.kt").is_file())


if __name__ == "__main__":
    unittest.main()
