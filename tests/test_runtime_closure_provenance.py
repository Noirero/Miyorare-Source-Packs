import inspect
import unittest

from tools.runtime_closure_provenance import build_proof, derive_paths, executed_project_roots, exercised_classes


class RuntimeClosureProvenanceTest(unittest.TestCase):
    def test_records_only_changed_paths_in_executed_projects_and_build_inputs(self):
        log = "\n".join([
            "> Task :core:compileKotlin",
            "> Task :lib-multisrc:madara:compileKotlin",
            "> Task :src:en:aquamanga:testDebugUnitTest",
        ])
        roots = executed_project_roots(log)
        changed = {
            "core/src/main/kotlin/keiyoushi/utils/WebView.kt",
            "lib-multisrc/madara/src/eu/kanade/tachiyomi/multisrc/madara/Madara.kt",
            "src/en/aquamanga/build.gradle.kts",
            "src/en/aquamanga/src/eu/kanade/tachiyomi/extension/en/aquamanga/AquaManga.kt",
            "src/en/unrelated/Unrelated.kt",
            "gradle.properties",
        }
        paths = derive_paths(changed, roots)
        self.assertIn("core/src/main/kotlin/keiyoushi/utils/WebView.kt", paths)
        self.assertIn("lib-multisrc/madara/src/eu/kanade/tachiyomi/multisrc/madara/Madara.kt", paths)
        self.assertIn("src/en/aquamanga/build.gradle.kts", paths)
        self.assertIn("gradle.properties", paths)
        self.assertNotIn("src/en/unrelated/Unrelated.kt", paths)

    def test_truncated_log_cannot_claim_target_module(self):
        roots = executed_project_roots("> Task :core:compileKotlin\n")
        self.assertNotIn("src/en/aquamanga", roots)

    def test_contract_vocabulary_uses_build_definition_not_legacy_build_script(self):
        classes = exercised_classes(
            "src/en/aquamanga",
            ["src/en/aquamanga/build.gradle.kts", "core/src/main/kotlin/keiyoushi/utils/WebView.kt"],
            True,
        )
        self.assertIn("build-definition-change", classes)
        self.assertIn("parser-code-change", classes)
        self.assertIn("module-resource-or-structure-change", classes)
        self.assertIn("shared-runtime-change", classes)
        self.assertNotIn("build-script-change", classes)

    def test_failed_execution_claims_no_change_classes(self):
        self.assertEqual([], exercised_classes("src/en/aquamanga", ["gradle.properties"], False))

    def test_proof_carries_exact_base_revision_for_farm_aggregation(self):
        source = inspect.getsource(build_proof)
        self.assertIn('"baseRevision": base', source)
        self.assertIn('"candidateRevision": candidate', source)
        self.assertIn('"runtimeClosureRevision": candidate', source)


if __name__ == "__main__":
    unittest.main()
