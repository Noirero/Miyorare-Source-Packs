import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "source_inventory",
    Path(__file__).parents[1] / "tools/source_inventory.py",
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mod)


class SourceInventoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.kei = self.root / "kei"
        self.uma = self.root / "uma"
        self.gek = self.root / "gek"
        for path in (self.kei, self.uma, self.gek):
            path.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, root, rel, text):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_explicit_mapping_and_keiyoushi_id(self):
        self.write(
            self.kei,
            "src/id/komiku/build.gradle.kts",
            '''
keiyoushi {
  name = "Komiku"
  versionCode = 1
  source { lang = "id"; baseUrl = "https://komiku.org" }
}
''',
        )
        self.write(
            self.uma,
            "src/main/kotlin/tsuki/site/id/Komiku.kt",
            '@MangaSourceParser("KOMIKU", "Komiku", "id")\n',
        )
        aliases = {
            "aliases": [
                {
                    "canonicalId": "miyorare:miyorare-id:KOMIKU",
                    "language": "id",
                    "official": {"sourceName": "Komiku"},
                    "uma": {
                        "file": "src/main/kotlin/tsuki/site/id/Komiku.kt",
                        "sourceName": "KOMIKU",
                    },
                    "keiyoushi": {
                        "module": "src/id/komiku",
                        "sourceName": "Komiku",
                        "sourceId": mod.compute_keiyoushi_source_id("Komiku", "id"),
                    },
                }
            ]
        }
        value = mod.build_inventory(
            self.kei,
            self.uma,
            self.gek,
            aliases,
            {},
            {},
            {provider: "a" * 40 for provider in mod.PROVIDERS},
        )
        self.assertEqual(1, len(value["sources"]))
        source = value["sources"][0]
        self.assertEqual("miyorare:miyorare-id:KOMIKU", source["canonicalId"])
        self.assertEqual({"keiyoushi", "uma"}, set(source["providers"]))
        self.assertFalse(source["needsAttention"])

    def test_exact_name_merges_one_identity_per_provider(self):
        self.write(
            self.uma,
            "src/main/kotlin/tsuki/site/en/Foo.kt",
            '@MangaSourceParser("FOO", "Foo Scans", "en")',
        )
        self.write(
            self.gek,
            "src/main/kotlin/tsuki/site/en/FooParser.kt",
            '@MangaSourceParser("FOO", "Foo Scans", "en")',
        )
        value = mod.build_inventory(
            self.kei,
            self.uma,
            self.gek,
            {},
            {},
            {},
            {provider: "b" * 40 for provider in mod.PROVIDERS},
        )
        self.assertEqual(1, len(value["sources"]))
        source = value["sources"][0]
        self.assertEqual("exact-name", source["identityConfidence"])
        self.assertEqual({"uma", "gekkoushi"}, set(source["providers"]))

    def test_same_provider_name_collision_is_separate_and_attention_required(self):
        self.write(
            self.uma,
            "src/main/kotlin/tsuki/site/en/Foo.kt",
            '@MangaSourceParser("FOO1", "Foo", "en")',
        )
        self.write(
            self.uma,
            "src/main/kotlin/tsuki/site/en/Foo2.kt",
            '@MangaSourceParser("FOO2", "Foo", "en")',
        )
        value = mod.build_inventory(
            self.kei,
            self.uma,
            self.gek,
            {},
            {},
            {},
            {provider: "c" * 40 for provider in mod.PROVIDERS},
        )
        self.assertEqual(2, len(value["sources"]))
        self.assertTrue(all(source["needsAttention"] for source in value["sources"]))
        self.assertEqual(2, len({source["canonicalId"] for source in value["sources"]}))

    def test_previous_inventory_preserves_canonical_identity(self):
        self.write(
            self.uma,
            "src/main/kotlin/tsuki/site/en/Foo.kt",
            '@MangaSourceParser("FOO", "Foo Renamed", "en")',
        )
        previous = {
            "sources": [
                {
                    "canonicalId": "miyorare:inventory-en:FOO-STABLE",
                    "providers": {
                        "uma": {
                            "file": "src/main/kotlin/tsuki/site/en/Foo.kt",
                            "sourceName": "FOO",
                        }
                    },
                }
            ]
        }
        value = mod.build_inventory(
            self.kei,
            self.uma,
            self.gek,
            {},
            {},
            previous,
            {provider: "d" * 40 for provider in mod.PROVIDERS},
        )
        self.assertEqual(
            "miyorare:inventory-en:FOO-STABLE",
            value["sources"][0]["canonicalId"],
        )
        self.assertEqual("previous", value["sources"][0]["identityConfidence"])

    def test_validation_rejects_duplicate_provider_identity(self):
        value = {
            "schemaVersion": 1,
            "kind": "MIYORARE_SOURCE_INVENTORY",
            "informationalOnly": True,
            "stats": {"allSources": 2},
            "sources": [
                {
                    "canonicalId": "miyorare:x:A",
                    "providers": {"uma": {"file": "x.kt", "sourceName": "X"}},
                },
                {
                    "canonicalId": "miyorare:x:B",
                    "providers": {"uma": {"file": "x.kt", "sourceName": "X"}},
                },
            ],
        }
        with self.assertRaises(ValueError):
            mod.validate_inventory(value)


if __name__ == "__main__":
    unittest.main()
