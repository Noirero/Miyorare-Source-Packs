import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p1c", ROOT / "tools/validate_workflow_permissions.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class WorkflowPermissionPolicyTests(unittest.TestCase):
    def policy(self):
        return MODULE.load_policy(ROOT / "governance/workflow-permission-policy.v1.json")

    def test_repository_workflows_pass_policy(self):
        self.assertEqual([], MODULE.audit(ROOT / ".github/workflows", self.policy()))

    def test_implicit_permissions_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.yml").write_text("name: bad\non: workflow_dispatch\njobs:\n  x:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
            errors = MODULE.audit(root, self.policy())
            self.assertTrue(any("explicit top-level permissions" in error for error in errors))

    def test_unlisted_write_permission_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.yml").write_text("name: bad\non: workflow_dispatch\npermissions:\n  contents: write\n", encoding="utf-8")
            errors = MODULE.audit(root, self.policy())
            self.assertTrue(any("unapproved contents: write" in error for error in errors))

    def test_broad_permission_alias_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.yml").write_text("name: bad\non: workflow_dispatch\npermissions: write-all\n", encoding="utf-8")
            errors = MODULE.audit(root, self.policy())
            self.assertTrue(any("write-all/read-all" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
