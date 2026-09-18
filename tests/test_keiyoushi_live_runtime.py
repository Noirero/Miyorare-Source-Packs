#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "keiyoushi_live_runtime", ROOT / "tools" / "keiyoushi_live_runtime.py"
)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class KeiyoushiLiveRuntimeTest(unittest.TestCase):
    def test_materialize_removes_fixture_interceptor_only_from_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "runtime"
            network = source / "eu/kanade/tachiyomi/network/NetworkShim.kt"
            factory = source / "eu/kanade/tachiyomi/source/SourceFactoryShim.kt"
            network.parent.mkdir(parents=True)
            factory.parent.mkdir(parents=True)
            network.write_text(
                "class NetworkHelper {\n"
                "    val client = OkHttpClient.Builder()\n"
                "        .addInterceptor(DeterministicFixtureInterceptor())\n"
                "        .build()\n"
                "}\n",
                encoding="utf-8",
            )
            factory.write_text("interface SourceFactory\n", encoding="utf-8")
            target = root / "module-runtime"

            result = runtime.materialize(source, target)

            self.assertEqual(result["mode"], "real-live-network")
            self.assertIn(
                runtime.FIXTURE_LINE,
                network.read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                runtime.FIXTURE_LINE,
                (target / "eu/kanade/tachiyomi/network/NetworkShim.kt").read_text(encoding="utf-8"),
            )
            self.assertTrue(
                (target / "eu/kanade/tachiyomi/source/SourceFactoryShim.kt").is_file(),
            )

    def test_materialize_fails_closed_when_runtime_contract_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "runtime"
            network = source / "eu/kanade/tachiyomi/network/NetworkShim.kt"
            factory = source / "eu/kanade/tachiyomi/source/SourceFactoryShim.kt"
            network.parent.mkdir(parents=True)
            factory.parent.mkdir(parents=True)
            network.write_text("class NetworkHelper\n", encoding="utf-8")
            factory.write_text("interface SourceFactory\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "interceptor marker missing"):
                runtime.materialize(source, root / "target")


if __name__ == "__main__":
    unittest.main()
