#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

SHA40 = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)")


def load_policy(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1 or data.get("kind") != "MIYORARE_GITHUB_ACTION_PIN_POLICY":
        raise SystemExit("invalid action pin policy")
    approved = data.get("approved")
    if not isinstance(approved, dict) or not approved:
        raise SystemExit("action pin policy has no approved actions")
    by_action = {}
    for action, versions in approved.items():
        if not isinstance(versions, dict) or not versions:
            raise SystemExit(f"invalid approved pin set for {action}")
        pins = set()
        for label, sha in versions.items():
            if not isinstance(label, str) or not isinstance(sha, str) or not SHA40.fullmatch(sha):
                raise SystemExit(f"invalid approved pin {action}@{label}")
            pins.add(sha)
        by_action[action] = pins
    return by_action


def validate(workflows: Path, policy: Path):
    approved = load_policy(policy)
    failures = []
    checked = 0
    for path in sorted(workflows.glob("*.yml")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = USES.match(line)
            if not match:
                continue
            ref = match.group(1)
            if ref.startswith("./"):
                continue
            if "@" not in ref:
                failures.append(f"{path}:{lineno}: external action has no immutable ref: {ref}")
                continue
            action, revision = ref.rsplit("@", 1)
            checked += 1
            if not SHA40.fullmatch(revision):
                failures.append(f"{path}:{lineno}: moving/non-SHA action ref: {ref}")
                continue
            allowed = approved.get(action)
            if allowed is None:
                failures.append(f"{path}:{lineno}: action is not in approved pin policy: {action}")
            elif revision not in allowed:
                failures.append(f"{path}:{lineno}: unapproved immutable revision for {action}: {revision}")
    if failures:
        raise SystemExit("Action pin validation failed:\n" + "\n".join(failures))
    print(f"Action pin validation passed: {checked} external action uses are immutable and approved")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflows", default=".github/workflows")
    parser.add_argument("--policy", default="governance/action-pins.v1.json")
    args = parser.parse_args()
    validate(Path(args.workflows), Path(args.policy))


if __name__ == "__main__":
    main()
