import json
import tempfile
import unittest
from pathlib import Path

from tools.validate_action_pins import validate


POLICY = Path("governance/action-pins.v1.json")


class ActionPinTests(unittest.TestCase):
    def run_case(self, workflow_text, should_pass):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "test.yml").write_text(workflow_text, encoding="utf-8")
            if should_pass:
                validate(workflows, POLICY)
            else:
                with self.assertRaises(SystemExit):
                    validate(workflows, POLICY)

    def test_repository_workflows_are_fully_pinned(self):
        validate(Path(".github/workflows"), POLICY)

    def test_moving_tag_is_rejected(self):
        self.run_case("steps:\n  - uses: actions/checkout@v5\n", False)

    def test_unknown_sha_is_rejected(self):
        self.run_case("steps:\n  - uses: actions/checkout@" + "0" * 40 + "\n", False)

    def test_local_reusable_workflow_is_allowed(self):
        self.run_case("jobs:\n  x:\n    uses: ./.github/workflows/local.yml\n", True)

    def test_policy_contains_only_sha_pins(self):
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        for versions in data["approved"].values():
            for sha in versions.values():
                self.assertRegex(sha, r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
