import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from source_shape_guard import ShapeError, validate_shapes  # noqa: E402


class SourceShapeGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "compatibility/source-registry.json").read_text(encoding="utf-8"))
        cls.fixtures = json.loads(
            (ROOT / "compatibility/fixtures/deterministic-seed-3.json").read_text(encoding="utf-8")
        )
        cls.families = json.loads((ROOT / "compatibility/adapter-families.json").read_text(encoding="utf-8"))

    def _write_uma_sources(self, root: Path):
        samples = {
            "src/main/kotlin/tsuki/site/id/Komiku.kt": '''
@MangaSourceParser("KOMIKU", "Komiku", "id")
class Komiku : MangaReaderParser(context, source, "komiku.org", 10, 10) {
  val apiDomain = "api.komiku.org"
  val selectPage = "#Baca_Komik img"
  val selectChapter = "#Daftar_Chapter tr"
}
''',
            "src/main/kotlin/tsuki/site/id/Shinigami.kt": '''
@MangaSourceParser("SHINIGAMI", "Shinigami", "id")
class Shinigami : PagedMangaParser(context, source, 30) {
  fun getRequestHeaders() = Unit
  fun parseJson() = Unit
  fun getPages() = Unit
}
''',
            "src/main/kotlin/tsuki/site/en/WeebCentral.kt": '''
@MangaSourceParser("WEEBCENTRAL", "Weeb Central", "en")
class WeebCentral : MangaParserAuthProvider {
  fun isAuthorized() = getCookies().any { it.name == "access_token" }
  fun getCookies() = emptyList<Any>()
  fun getPages() = Unit
}
''',
        }
        for relative, content in samples.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def test_seed_sources_match_family_shapes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_uma_sources(root)
            report = validate_shapes(self.registry, self.fixtures, self.families, "uma", root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["checked"], 3)
        self.assertEqual(report["failed"], 0)

    def test_missing_auth_signal_fails_shape_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_uma_sources(root)
            path = root / "src/main/kotlin/tsuki/site/en/WeebCentral.kt"
            path.write_text(path.read_text(encoding="utf-8").replace("access_token", "session"), encoding="utf-8")
            report = validate_shapes(self.registry, self.fixtures, self.families, "uma", root)
        target = next(item for item in report["results"] if item["canonicalId"].endswith(":WEEBCENTRAL"))
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(target["status"], "FAIL")
        self.assertIn(["access_token"], target["missingTokenGroups"])

    def test_unknown_adapter_family_is_fail_closed(self):
        registry = copy.deepcopy(self.registry)
        target = next(item for item in registry["sources"] if item["canonicalId"].endswith(":KOMIKU"))
        target["adapterFamily"] = "brand-new-unknown-family"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_uma_sources(root)
            with self.assertRaises(ShapeError):
                validate_shapes(registry, self.fixtures, self.families, "uma", root)


if __name__ == "__main__":
    unittest.main()
