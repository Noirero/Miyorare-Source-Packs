import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "keiyoushi_intake",
    Path(__file__).resolve().parents[1] / "tools" / "keiyoushi_intake.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class KeiyoushiIntakeTests(unittest.TestCase):
    def test_metadata_only_build_change_is_validate_only(self):
        diff = "@@ -1 +1 @@\n-    versionCode = 9\n+    versionCode = 10\n"
        with patch.object(MODULE, "diff_for_path", return_value=diff):
            result = MODULE.classify_module(
                Path("."),
                "0" * 40,
                "1" * 40,
                "src/id/example",
                ["src/id/example/build.gradle.kts"],
                False,
            )
        self.assertEqual("metadata-only", result["state"])
        self.assertEqual("validate-only", result["action"])

    def test_base_url_change_requires_semantic_adapter(self):
        diff = "@@ -1 +1 @@\n-        baseUrl = \"https://old.example\"\n+        baseUrl = \"https://new.example\"\n"
        with patch.object(MODULE, "diff_for_path", return_value=diff):
            result = MODULE.classify_module(
                Path("."),
                "0" * 40,
                "1" * 40,
                "src/id/example",
                ["src/id/example/build.gradle.kts"],
                False,
            )
        self.assertEqual("semantic-adapter-candidate", result["state"])
        self.assertEqual("adapter-required", result["action"])
        self.assertIn("semantic-config-change", result["changeClasses"])

    def test_literal_only_kotlin_change_requires_semantic_adapter(self):
        diff = (
            '@@ -1 +1 @@\n'
            '-    override val selectPage = "#reader img"\n'
            '+    override val selectPage = "#reader-area img"\n'
        )
        with patch.object(MODULE, "diff_for_path", return_value=diff):
            result = MODULE.classify_module(
                Path("."),
                "0" * 40,
                "1" * 40,
                "src/id/example",
                ["src/id/example/src/example/Example.kt"],
                False,
            )
        self.assertEqual("semantic-adapter-candidate", result["state"])
        self.assertEqual("adapter-required", result["action"])
        self.assertIn("literal-semantic-change", result["changeClasses"])

    def test_structural_parser_kotlin_change_is_held(self):
        diff = (
            '@@ -1 +1 @@\n'
            '-    override val selectPage = "#reader img"\n'
            '+    override fun pages() = select("#reader-area img")\n'
        )
        with patch.object(MODULE, "diff_for_path", return_value=diff):
            result = MODULE.classify_module(
                Path("."),
                "0" * 40,
                "1" * 40,
                "src/id/example",
                ["src/id/example/src/example/Example.kt"],
                False,
            )
        self.assertEqual("review-required", result["state"])
        self.assertEqual("hold-unless-reusable-adapter-supports-change", result["action"])
        self.assertIn("parser-code-change", result["changeClasses"])

    def test_adapter_coverage_allows_literal_semantic_change(self):
        result = {
            "state": "semantic-adapter-candidate",
            "action": "adapter-required",
            "changeClasses": ["literal-semantic-change"],
            "files": [],
        }
        adapted = MODULE.apply_adapter_coverage(
            "miyorare:miyorare-id:EXAMPLE",
            result,
            {"miyorare:miyorare-id:EXAMPLE": {"literal-semantic"}},
        )
        self.assertEqual("adapted", adapted["state"])
        self.assertEqual("validate-adapter-output", adapted["action"])

    def test_shared_runtime_change_affects_registered_source(self):
        result = MODULE.classify_module(
            Path("."),
            "0" * 40,
            "1" * 40,
            "src/id/example",
            [],
            True,
        )
        self.assertEqual("review-required", result["state"])
        self.assertIn("shared-runtime-change", result["changeClasses"])


if __name__ == "__main__":
    unittest.main()
