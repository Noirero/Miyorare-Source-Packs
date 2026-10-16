"""Exercise the real overlay steps and pinned builder without modifying fixture checkouts."""

import argparse
import contextlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


LEGACY = Path("src/main/kotlin/tsuki/site/madara/ko/RawDex.kt")
REPLACEMENT = Path("src/main/kotlin/tsuki/site/all/RawDex.kt")
SOURCE_PACK = Path("extensions/miyorare-sources")
JOBS = ("validate-gekkoushi", "integration")


class RawDexIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = Path(ARGS.miyorare_root).resolve()
        cls.upstream = Path(ARGS.gekkoushi_root).resolve()
        workflow = json.loads(Path(ARGS.workflow_json).read_text(encoding="utf-8"))
        cls.steps = {}
        for job in JOBS:
            steps = [
                step for step in workflow["jobs"][job]["steps"]
                if step.get("name") == "Apply matching Miyorare overlays"
            ]
            if len(steps) != 1:
                raise AssertionError(f"Expected exactly one overlay step in {job}")
            if steps[0]["env"]["PACK"] != "${{ matrix.pack }}":
                raise AssertionError(f"Overlay pack scope changed in {job}")
            cls.steps[job] = steps[0]["run"]

        sys.dont_write_bytecode = True
        sys.path.insert(0, str(cls.builder / SOURCE_PACK / "tools"))
        cls.collector = importlib.import_module("prepare_gekkoushi_shard")
        cls.preparer = importlib.import_module("prepare_global_gekkoushi_shard")

    @contextlib.contextmanager
    def checkout(self):
        with tempfile.TemporaryDirectory(prefix="rawdex-integration-") as temporary:
            root = Path(temporary)
            shutil.copytree(self.upstream, root / "_upstream/gekkoushi")
            shutil.copytree(self.builder / SOURCE_PACK, root / "miyorare" / SOURCE_PACK)
            yield root

    def apply_overlays(self, root, job, pack):
        subprocess.run(
            ["bash", "-euo", "pipefail", "-c", self.steps[job]],
            cwd=root,
            env={**os.environ, "PACK": pack},
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def assert_global_preparation(self, root):
        upstream = root / "_upstream/gekkoushi"
        replacement = root / "miyorare" / SOURCE_PACK / "overlays/gekkoushi/all/RawDex.kt"
        self.assertFalse((upstream / LEGACY).exists())
        self.assertEqual(replacement.read_bytes(), (upstream / REPLACEMENT).read_bytes())
        names, locales, _, _ = self.collector.collect_sources(upstream / "src/main/kotlin/tsuki/site")
        self.assertEqual(1, names.count("RAWDEX"))
        self.assertEqual("all", locales["RAWDEX"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.preparer.prepare(root / "miyorare" / SOURCE_PACK / "packs.json", upstream, "global")
        metadata = json.loads((upstream / "miyorare-pack.json").read_text(encoding="utf-8"))
        self.assertEqual("miyorare-global", metadata["pluginId"])
        self.assertEqual(["EXHENTAI", "GELBOORU", "NEWXTOON", "RAWDEX"], metadata["sourceNames"])
        self.assertEqual(1, metadata["compiledSourceNames"].count("RAWDEX"))

    def test_both_global_paths_prepare_the_authoritative_replacement(self):
        for job in JOBS:
            with self.subTest(job=job), self.checkout() as root:
                self.apply_overlays(root, job, "global")
                self.assert_global_preparation(root)
        self.assertTrue((self.upstream / LEGACY).is_file())
        self.assertFalse((self.upstream / REPLACEMENT).exists())

    def test_id_and_en_keep_legacy_and_apply_only_their_own_overlays(self):
        for job in JOBS:
            for pack in ("id", "en"):
                with self.subTest(job=job, pack=pack), self.checkout() as root:
                    upstream = root / "_upstream/gekkoushi"
                    before = (upstream / LEGACY).read_bytes()
                    self.apply_overlays(root, job, pack)
                    self.assertEqual(before, (upstream / LEGACY).read_bytes())
                    self.assertFalse((upstream / REPLACEMENT).exists())
                    overlays = root / "miyorare" / SOURCE_PACK / "overlays/gekkoushi" / pack
                    for source in overlays.rglob("*.kt"):
                        target = upstream / "src/main/kotlin/tsuki/site" / pack / source.relative_to(overlays)
                        self.assertEqual(source.read_bytes(), target.read_bytes())

    def test_missing_replacement_preserves_legacy(self):
        for job in JOBS:
            with self.subTest(job=job), self.checkout() as root:
                overlay = root / "miyorare" / SOURCE_PACK / "overlays/gekkoushi/all/RawDex.kt"
                overlay.unlink()
                upstream = root / "_upstream/gekkoushi"
                before = (upstream / LEGACY).read_bytes()
                self.apply_overlays(root, job, "global")
                self.assertEqual(before, (upstream / LEGACY).read_bytes())
                self.assertFalse((upstream / REPLACEMENT).exists())

    def test_unrelated_duplicates_still_fail(self):
        for job in JOBS:
            with self.subTest(job=job), self.checkout() as root:
                self.apply_overlays(root, job, "global")
                sites = root / "_upstream/gekkoushi/src/main/kotlin/tsuki/site"
                for name in ("DuplicateOne.kt", "DuplicateTwo.kt"):
                    (sites / "all" / name).write_text(
                        '@MangaSourceParser("FIXB_DUPLICATE", "Duplicate", "all")\n',
                        encoding="utf-8",
                    )
                with self.assertRaisesRegex(SystemExit, "duplicate runtime source name: FIXB_DUPLICATE"):
                    self.collector.collect_sources(sites)

    def test_replacement_is_idempotent_without_legacy(self):
        for job in JOBS:
            with self.subTest(job=job), self.checkout() as root:
                self.apply_overlays(root, job, "global")
                self.apply_overlays(root, job, "global")
                self.assert_global_preparation(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-json", required=True)
    parser.add_argument("--miyorare-root", required=True)
    parser.add_argument("--gekkoushi-root", required=True)
    parser.add_argument("--stage-global", type=Path)
    ARGS = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RawDexIntegrationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    if ARGS.stage_global:
        stage = ARGS.stage_global.resolve()
        stage.mkdir(parents=True, exist_ok=False)
        with RawDexIntegrationTests().checkout() as root:
            case = RawDexIntegrationTests()
            case.apply_overlays(root, "integration", "global")
            case.assert_global_preparation(root)
            shutil.copytree(root / "_upstream/gekkoushi", stage / "gekkoushi")
