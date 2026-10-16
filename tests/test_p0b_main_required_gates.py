from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class P0BMainRequiredGateTests(unittest.TestCase):
    def test_main_gate_is_unconditionally_present_on_main_prs(self) -> None:
        gate = (WORKFLOWS / "main-required-gates.yml").read_text(encoding="utf-8")
        self.assertIn("name: Main Required Gates", gate)
        self.assertIn("pull_request:\n    branches: [main]", gate)
        self.assertNotIn("pull_request:\n    branches: [main]\n    paths:", gate)
        self.assertNotIn("workflow_dispatch:", gate)
        self.assertIn("name: Main Required Gates\n    runs-on:", gate)

    def test_core_gates_are_dispatched_and_bound_to_exact_head(self) -> None:
        gate = (WORKFLOWS / "main-required-gates.yml").read_text(encoding="utf-8")
        for workflow in (
            "source-pack-contract.yml",
            "source-pack-builder-baseline.yml",
            "source-inventory-ci.yml",
        ):
            self.assertIn(workflow, gate)
        self.assertIn('select(.headSha == \\"$HEAD_SHA\\")', gate)
        self.assertIn("gh run watch", gate)
        self.assertIn("PR head moved after required-gate validation", gate)

    def test_relevant_changed_file_gates_fail_closed(self) -> None:
        gate = (WORKFLOWS / "main-required-gates.yml").read_text(encoding="utf-8")
        for workflow in (
            "upstream-sync-pr-check.yml",
            "source-lab-control-plane-ci.yml",
            "repair-android-sdk-setup.yml",
        ):
            self.assertIn(workflow, gate)
        self.assertIn("Required changed-file workflow $workflow did not run on exact PR head.", gate)

    def test_inventory_supports_exact_head_dispatch(self) -> None:
        inventory = (WORKFLOWS / "source-inventory-ci.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", inventory)


if __name__ == "__main__":
    unittest.main()
