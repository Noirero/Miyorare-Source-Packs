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


class DependencyScopeTests(unittest.TestCase):
    def test_natsuid_only_affects_module_using_natsuid(self):
        with patch.object(MODULE, "module_themes", return_value={"natsuid"}):
            self.assertEqual(
                "dependency",
                MODULE.shared_path_scope(Path("."), "1" * 40, "src/id/kiryuu", "lib-multisrc/natsuid/src/Dto.kt"),
            )
        with patch.object(MODULE, "module_themes", return_value={"madaralegacy"}):
            self.assertEqual(
                "none",
                MODULE.shared_path_scope(Path("."), "1" * 40, "src/en/aquamanga", "lib-multisrc/natsuid/src/Dto.kt"),
            )

    def test_dependency_scoped_shared_change_is_auto_repairable(self):
        result = MODULE.classify_module(
            Path("."),
            "0" * 40,
            "1" * 40,
            "src/id/kiryuu",
            [],
            ["lib-multisrc/natsuid/src/Dto.kt"],
        )
        self.assertEqual("dependency-validation-required", result["state"])
        self.assertEqual("AUTO-REPAIRABLE", result["automationClass"])
        self.assertEqual("validate-dependent-runtime", result["action"])

    def test_unrelated_shared_change_does_not_affect_source(self):
        result = MODULE.classify_module(Path("."), "0" * 40, "1" * 40, "src/id/bacami", [], [])
        self.assertEqual("unaffected", result["state"])
        self.assertEqual("AUTO-SAFE", result["automationClass"])

    def test_global_shared_change_stays_fail_closed(self):
        result = MODULE.classify_module(
            Path("."),
            "0" * 40,
            "1" * 40,
            "src/id/example",
            [],
            ["common/src/main/kotlin/Shared.kt"],
            global_shared_change=True,
        )
        self.assertEqual("review-required", result["state"])
        self.assertEqual("NEEDS_REVIEW", result["automationClass"])


if __name__ == "__main__":
    unittest.main()
