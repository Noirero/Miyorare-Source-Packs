import importlib.util
import json
import subprocess
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
            self.assertEqual(2, report["schema"])
            self.assertEqual(["miyorare:miyorare-id:EXAMPLE"], report["appliedCanonicalIds"])
            self.assertIn('"new.example"', uma_file.read_text(encoding="utf-8"))
            updated_aliases = json.loads(aliases.read_text(encoding="utf-8"))
            self.assertEqual("new.example", updated_aliases["aliases"][0]["verifiedDomain"])
            change = report["applied"][0]["changes"][0]
            self.assertEqual("domain-base-url", change["changeClass"])
            self.assertEqual("literal-host-rewrite", change["mode"])

    def test_accepts_already_compatible_uma_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            aliases, kei, uma, _ = self.make_fixture(
                root,
                'class Example : Parser("new.example")\n',
            )
            report = MODULE.apply_domain_adapters(aliases, kei, uma)
            self.assertEqual("clear", report["state"])
            change = report["applied"][0]["changes"][0]
            self.assertEqual("already-compatible", change["mode"])

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

    def test_extracts_literal_only_selector_change(self):
        diff = (
            '@@ -1 +1 @@\n'
            '-    override val selectPage = "#reader img"\n'
            '+    override val selectPage = "#reader-area img"\n'
        )
        pairs, unsupported = MODULE.changed_literal_pairs(diff)
        self.assertFalse(unsupported)
        self.assertEqual([("#reader img", "#reader-area img")], pairs)

    def test_rejects_structural_parser_change_as_literal_only(self):
        diff = (
            '@@ -1 +1 @@\n'
            '-    override val selectPage = "#reader img"\n'
            '+    override fun pages() = select("#reader-area img")\n'
        )
        pairs, unsupported = MODULE.changed_literal_pairs(diff)
        self.assertTrue(unsupported)
        self.assertEqual([], pairs)

    def test_unique_literal_semantic_rewrite(self):
        text = 'override val selectPage = "#reader img"\n'
        updated, detail, reason = MODULE.apply_literal_pair(
            text,
            "#reader img",
            "#reader-area img",
            set(),
        )
        self.assertIsNone(reason)
        self.assertIsNotNone(detail)
        self.assertIn('"#reader-area img"', updated)
        self.assertEqual("unique-literal-rewrite", detail["mode"])

    def test_literal_semantic_rejects_kind_change(self):
        text = 'override val selectPage = "#reader img"\n'
        _, detail, reason = MODULE.apply_literal_pair(
            text,
            "#reader img",
            "https://example.org/pages",
            set(),
        )
        self.assertIsNone(detail)
        self.assertEqual("literal-kind-changed:selector-to-url", reason)

    def test_generic_literal_is_refused_before_guessing(self):
        text = 'val sourceName = "EXAMPLE"\n'
        _, detail, reason = MODULE.apply_literal_pair(
            text,
            "EXAMPLE",
            "EXAMPLE2",
            set(),
        )
        self.assertIsNone(detail)
        self.assertEqual("unsupported-or-too-generic-literal", reason)

    def test_literal_semantic_refuses_protected_identity(self):
        text = 'val host = "old.example"\n'
        _, detail, reason = MODULE.apply_literal_pair(
            text,
            "old.example",
            "new.example",
            {"old.example"},
        )
        self.assertIsNone(detail)
        self.assertEqual("protected-identity-literal", reason)

    def test_blocked_literal_rolls_back_pending_domain_and_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            aliases, kei, uma, uma_file = self.make_fixture(
                root,
                'class Example : Parser("old.example") {\n'
                '    val selector = "#old-list"\n'
                '}\n',
            )
            module = kei / "src/id/example"
            source = module / "src/Example.kt"
            source.parent.mkdir(parents=True)

            # Build an actual two-commit Keiyoushi history so the adapter reads a real semantic diff.
            (module / "build.gradle.kts").write_text(
                'keiyoushi {\n  source {\n    lang = "id"\n    baseUrl = "https://old.example"\n  }\n}\n',
                encoding="utf-8",
            )
            source.write_text('val selector = "#old-list"\n', encoding="utf-8")
            subprocess.run(["git", "init"], cwd=kei, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=kei, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=kei, check=True)
            subprocess.run(["git", "add", "."], cwd=kei, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=kei, check=True, stdout=subprocess.DEVNULL)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=kei, text=True).strip()

            (module / "build.gradle.kts").write_text(
                'keiyoushi {\n  source {\n    lang = "id"\n    baseUrl = "https://new.example"\n  }\n}\n',
                encoding="utf-8",
            )
            source.write_text('val selector = "https://new.example/pages"\n', encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=kei, check=True)
            subprocess.run(["git", "commit", "-m", "candidate"], cwd=kei, check=True, stdout=subprocess.DEVNULL)
            candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=kei, text=True).strip()

            report = MODULE.apply_semantic_adapters(
                aliases,
                kei,
                uma,
                base=base,
                candidate=candidate,
                capabilities={"domain-base-url", "literal-semantic"},
            )

            self.assertEqual("blocked", report["state"])
            self.assertIn("literal-kind-changed:selector-to-url", [item["reason"] for item in report["blocked"]])
            self.assertIn('"old.example"', uma_file.read_text(encoding="utf-8"))
            self.assertIn('"#old-list"', uma_file.read_text(encoding="utf-8"))
            updated_aliases = json.loads(aliases.read_text(encoding="utf-8"))
            self.assertEqual("old.example", updated_aliases["aliases"][0]["verifiedDomain"])


if __name__ == "__main__":
    unittest.main()
