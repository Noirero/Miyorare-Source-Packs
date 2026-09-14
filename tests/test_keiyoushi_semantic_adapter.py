import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "keiyoushi_semantic_adapter",
    Path(__file__).resolve().parents[1] / "tools" / "keiyoushi_semantic_adapter.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class KeiyoushiSemanticAdapterTests(unittest.TestCase):
    def make_fixture(self, root: Path, uma_text: str):
        aliases = root / "multi-upstream.json"
        kei = root / "kei"
        uma = root / "uma"
        module = kei / "src/id/example"
        module.mkdir(parents=True)
        (module / "build.gradle.kts").write_text(
            'keiyoushi {\n  source {\n    lang = "id"\n    baseUrl = "https://new.example"\n  }\n}\n',
            encoding="utf-8",
        )
        uma_file = uma / "src/main/kotlin/tsuki/site/id/Example.kt"
        uma_file.parent.mkdir(parents=True)
        uma_file.write_text(uma_text, encoding="utf-8")
        aliases.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "aliases": [
                        {
                            "canonicalId": "miyorare:miyorare-id:EXAMPLE",
                            "verifiedDomain": "old.example",
                            "official": {"pack": "id", "pluginId": "miyorare-id", "sourceName": "EXAMPLE"},
                            "uma": {
                                "pluginId": "uma",
                                "sourceName": "EXAMPLE",
                                "file": "src/main/kotlin/tsuki/site/id/Example.kt",
                            },
                            "keiyoushi": {"module": "src/id/example", "sourceName": "Example", "sourceId": 1},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return aliases, kei, uma, uma_file

    def test_rewrites_safe_literal_host_and_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            aliases, kei, uma, uma_file = self.make_fixture(
                root,
                'class Example : Parser("old.example")\n',
            )
            report = MODULE.apply_domain_adapters(aliases, kei, uma)
            self.assertEqual("clear", report["state"])
            self.assertEqual(["miyorare:miyorare-id:EXAMPLE"], report["appliedCanonicalIds"])
            self.assertIn('"new.example"', uma_file.read_text(encoding="utf-8"))
            updated_aliases = json.loads(aliases.read_text(encoding="utf-8"))
            self.assertEqual("new.example", updated_aliases["aliases"][0]["verifiedDomain"])

    def test_accepts_already_compatible_uma_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            aliases, kei, uma, _ = self.make_fixture(
                root,
                'class Example : Parser("new.example")\n',
            )
            report = MODULE.apply_domain_adapters(aliases, kei, uma)
            self.assertEqual("clear", report["state"])
            self.assertEqual("already-compatible", report["applied"][0]["mode"])

    def test_blocks_ambiguous_domain_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            aliases, kei, uma, _ = self.make_fixture(
                root,
                'class Example : Parser(resolveDomainAtRuntime())\n',
            )
            report = MODULE.apply_domain_adapters(aliases, kei, uma)
            self.assertEqual("blocked", report["state"])
            self.assertEqual("old-verified-host-not-found-as-safe-uma-literal", report["blocked"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
