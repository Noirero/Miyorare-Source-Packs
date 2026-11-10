"""Regression tests for exact builder baseline promotion PR reuse (no GitHub writes)."""

import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/source-pack-autonomous-release.yml"
REPOSITORY = "Noirero/Miyorare-Source-Packs"
CANDIDATE = "dd806d8e289c7033c1f2e657b8ea2cf68756e23c"
HEAD = "a" * 40
PATH = "compatibility/miyorare-builder-baseline.json"


def baseline(commit=CANDIDATE):
    return {"schemaVersion": 1, "repository": "Noirero/Miyorare", "builderCommit": commit,
            "compatibilityEpoch": 1, "tsukiApi": "1.0.5"}


def pr(number=207, *, branch=None, author="github-actions[bot]", base="main", repo=REPOSITORY, sha=HEAD):
    return {"number": number, "base": {"ref": base},
            "head": {"ref": branch or f"automation/builder-baseline-{CANDIDATE[:12]}-{number}",
                     "repo": {"full_name": repo}, "sha": sha}, "user": {"login": author}}


def reuse_bash():
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if "# Reuse exact open PRs" in line)
    end = next(i for i in range(start + 1, len(lines)) if "git -C control config user.name" in lines[i])
    return textwrap.dedent("\n".join(lines[start:end]))


MOCK_GH = r'''#!/usr/bin/env python3
import base64, json, os, re, sys
args = sys.argv[1:]
assert args[0] == "api", args
url = next((a for a in args[1:] if a.startswith("repos/")), "")
with open(os.environ["FAKE_GH_DATA"], encoding="utf-8") as f:
    data = json.load(f)
if url.endswith("/pulls?state=open&per_page=100"):
    print(json.dumps(data["prs"]))
elif re.search(r"/pulls/\d+/files\?per_page=100$", url):
    n = re.search(r"/pulls/(\d+)/", url).group(1)
    print("\n".join(data["files"].get(n, [])))
elif "/contents/" in url and "?ref=" in url:
    sha = url.split("?ref=", 1)[1]
    if sha not in data["payloads"]:
        sys.exit(3)
    payload = json.dumps(data["payloads"][sha], indent=2) + "\n"
    print(base64.b64encode(payload.encode()).decode())
else:
    raise AssertionError(args)
'''

MOCK_GIT = r'''#!/usr/bin/env python3
import os, sys
with open(os.environ["FAKE_GIT_CALLS"], "a", encoding="utf-8") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
'''


class BuilderBaselinePrReuseTest(unittest.TestCase):
    def exercise(self, prs, *, files=None, payloads=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bindir = root / "bin"
            bindir.mkdir()
            for name, body in (("gh", MOCK_GH), ("git", MOCK_GIT)):
                dest = bindir / name
                dest.write_text(body, encoding="utf-8")
                dest.chmod(0o755)
            dest = root / "control" / PATH
            dest.parent.mkdir(parents=True)
            dest.write_text(json.dumps(baseline(), indent=2) + "\n", encoding="utf-8")
            (root / "api.json").write_text(json.dumps({
                "prs": prs, "files": files or {str(p["number"]): [PATH] for p in prs},
                "payloads": payloads if payloads is not None else {p["head"]["sha"]: baseline() for p in prs},
            }), encoding="utf-8")
            out = root / "outputs.txt"
            calls = root / "git_calls.txt"
            env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ["PATH"],
                       FAKE_GH_DATA=str(root / "api.json"), FAKE_GIT_CALLS=str(calls),
                       GITHUB_OUTPUT=str(out), GITHUB_REPOSITORY=REPOSITORY,
                       CANDIDATE_SHA=CANDIDATE)
            result = subprocess.run(["bash", "-euo", "pipefail", "-c", reuse_bash()],
                                    cwd=root, env=env, text=True, capture_output=True)
            return result.returncode, out.read_text() if out.exists() else "", \
                   calls.read_text() if calls.exists() else "", result.stderr

    def test_reuses_latest_matching_legacy_pr_on_rerun(self):
        prs = [pr(207), pr(206)]
        for _ in range(2):
            code, output, calls, stderr = self.exercise(prs)
            self.assertEqual(code, 0, stderr)
            self.assertIn("pr_number=207", output)
            self.assertIn("reused=true", output)
            self.assertEqual(calls, "", "no branch should be created on retry")

    def test_different_payload_or_extra_files_are_not_reused(self):
        prs = [pr(207, sha="b"*40), pr(206, sha="c"*40), pr(205)]
        files = {"207": [PATH, "README.md"], "206": [PATH], "205": [PATH]}
        payloads = {"b"*40: baseline(), "c"*40: baseline("f"*40), HEAD: baseline()}
        code, output, calls, stderr = self.exercise(prs, files=files, payloads=payloads)
        self.assertEqual(code, 0, stderr)
        self.assertIn("pr_number=205", output)
        self.assertEqual(calls, "")

    def test_foreign_or_unrelated_pr_not_reused(self):
        prs = [pr(207, author="someone"), pr(206, base="other"), pr(205, repo="Elsewhere/Fork")]
        code, output, calls, stderr = self.exercise(prs)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("reused=true", output)
        self.assertIn(f"switch -c automation/builder-baseline-{CANDIDATE}", calls)

    def test_new_candidate_uses_deterministic_branch_without_run_id(self):
        code, output, calls, stderr = self.exercise([])
        self.assertEqual(code, 0, stderr)
        self.assertIn(f"switch -c automation/builder-baseline-{CANDIDATE}", calls)
        self.assertEqual(output, "")

    def test_remote_validation_error_fails_closed(self):
        code, output, calls, _ = self.exercise([pr()], payloads={})
        self.assertNotEqual(code, 0)
        self.assertEqual(calls, "", "remote API failure must not create a new branch")

    def test_held_promotion_cannot_start_release(self):
        contents = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: false", contents)
        self.assertIn("steps.promote.outputs.reused != 'true'", contents)
        self.assertIn("steps.protected_gate.outputs.ready == 'true'", contents)
        self.assertIn("steps.builder.outputs.manifest_changed == 'false' || steps.promotion_merge.outputs.merged == 'true'", contents)
        self.assertIn("if: steps.desired.outcome == 'success'", contents)
        self.assertIn('gh pr merge "$PR_NUMBER"', contents)
        self.assertNotIn("--admin", contents)


if __name__ == "__main__":
    unittest.main()
