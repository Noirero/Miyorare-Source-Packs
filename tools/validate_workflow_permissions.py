#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PERMISSION_LINE = re.compile(r"^(?P<indent>\s*)(?P<scope>[a-z-]+):\s*(?P<level>read|write|none)\s*(?:#.*)?$")


def load_policy(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schemaVersion") != 1 or value.get("kind") != "MIYORARE_WORKFLOW_PERMISSION_POLICY":
        raise ValueError("unsupported workflow permission policy")
    return value


def permission_blocks(text: str) -> list[tuple[int, dict[str, str]]]:
    lines = text.splitlines()
    blocks: list[tuple[int, dict[str, str]]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)permissions:\s*$", line)
        if not match:
            continue
        indent = len(match.group(1))
        permissions: dict[str, str] = {}
        for child in lines[index + 1:]:
            if not child.strip() or child.lstrip().startswith("#"):
                continue
            child_indent = len(child) - len(child.lstrip())
            if child_indent <= indent:
                break
            parsed = PERMISSION_LINE.match(child)
            if parsed and len(parsed.group("indent")) > indent:
                permissions[parsed.group("scope")] = parsed.group("level")
        blocks.append((indent, permissions))
    return blocks


def audit(workflows: Path, policy: dict) -> list[str]:
    errors: list[str] = []
    authorities = {scope: set(names) for scope, names in policy["writeAuthorities"].items()}
    workflow_files = sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")])
    known_names = {path.name for path in workflow_files}

    for scope, names in authorities.items():
        unknown = names - known_names
        if unknown:
            errors.append(f"policy {scope} write authority references missing workflows: {sorted(unknown)}")

    for path in workflow_files:
        text = path.read_text(encoding="utf-8")
        if "write-all" in text or "read-all" in text:
            errors.append(f"{path.name}: broad write-all/read-all permission is forbidden")
        blocks = permission_blocks(text)
        top = [permissions for indent, permissions in blocks if indent == 0]
        if policy["rules"].get("requireExplicitTopLevelPermissions") and len(top) != 1:
            errors.append(f"{path.name}: requires exactly one explicit top-level permissions block")
        for _, permissions in blocks:
            for scope, level in permissions.items():
                if level == "write" and path.name not in authorities.get(scope, set()):
                    errors.append(f"{path.name}: unapproved {scope}: write")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--workflows", type=Path, required=True)
    args = parser.parse_args()
    errors = audit(args.workflows, load_policy(args.policy))
    if errors:
        raise SystemExit("Workflow permission audit failed:\n- " + "\n- ".join(errors))
    print("Workflow permission audit passed: explicit permissions and write authorities are least-privilege bounded")


if __name__ == "__main__":
    main()
