#!/usr/bin/env python3
"""Record exact runtime-closure provenance from a real Gradle execution.

This producer deliberately does not consume Source Lab intake/classifier output.
It intersects the exact baseline->candidate diff with project/build inputs proven
by the Gradle execution, leaving #114 as the independent fail-closed consumer.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

HEX40 = re.compile(r"^[0-9a-f]{40}$")
TASK_RE = re.compile(r"^> Task (:[^\s]+)")
ROOT_BUILD_INPUTS = {"build.gradle.kts", "settings.gradle.kts", "gradle.properties"}
BUILD_INPUT_PREFIXES = ("gradle/", "build-logic/", "buildSrc/")


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True)


def changed_paths(repo: Path, base: str, candidate: str) -> set[str]:
    if not HEX40.fullmatch(base) or not HEX40.fullmatch(candidate):
        raise ValueError("base and candidate must be exact 40-character git SHAs")
    return {line for line in git(repo, "diff", "--name-only", f"{base}..{candidate}").splitlines() if line}


def executed_project_roots(log_text: str) -> set[str]:
    roots: set[str] = set()
    for line in log_text.splitlines():
        match = TASK_RE.match(line.strip())
        if not match:
            continue
        parts = [part for part in match.group(1).split(":") if part]
        if len(parts) < 2:
            continue
        project = "/".join(parts[:-1])
        if project:
            roots.add(project)
    return roots


def is_under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def derive_paths(changed: set[str], roots: set[str]) -> list[str]:
    result = {
        path
        for path in changed
        if any(is_under(path, root) for root in roots)
        or path in ROOT_BUILD_INPUTS
        or path.startswith(BUILD_INPUT_PREFIXES)
    }
    return sorted(result)


def exercised_classes(module: str, paths: list[str], execution_succeeded: bool) -> list[str]:
    if not execution_succeeded:
        return []
    # These describe execution capabilities, not intake classification.  A
    # successful module test compiles/loads its parser, module definition and
    # resources plus the shared projects present in the actual Gradle task graph.
    classes = {"parser-code-change", "build-definition-change", "module-resource-or-structure-change"}
    if any(not is_under(path, module) for path in paths):
        classes.add("shared-runtime-change")
    return sorted(classes)


def build_proof(
    *, repo: Path, base: str, candidate: str, module: str, canonical: str,
    gradle_log: Path, webview: bool, job_status: str, run_id: str,
) -> dict:
    roots = executed_project_roots(gradle_log.read_text(encoding="utf-8", errors="replace"))
    module_root = module.rstrip("/")
    execution_succeeded = job_status == "success"
    # A PASS cannot be claimed unless the actual task graph contains the target
    # module itself.  This prevents a truncated/irrelevant log from manufacturing
    # apparently complete provenance.
    target_executed = module_root in roots
    result = "PASS" if execution_succeeded and target_executed else "FAIL"
    paths = derive_paths(changed_paths(repo, base, candidate), roots) if target_executed else []
    blocked = webview
    return {
        "schema": 1,
        "base": base,
        "candidate": candidate,
        "proofs": [{
            "canonicalId": canonical,
            "result": result,
            "infrastructureBlocked": blocked,
            "baseRevision": base,
            "candidateRevision": candidate,
            "runtimeClosureRevision": candidate,
            "evidenceId": f"github-run:{run_id}:{canonical}",
            "requiresAndroidWebView": webview,
            "androidWebViewExecutionProven": False,
            "executedRuntimeClosurePaths": paths,
            "exercisedChangeClasses": exercised_classes(module_root, paths, result == "PASS"),
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--gradle-log", type=Path, required=True)
    parser.add_argument("--webview", choices=("true", "false"), required=True)
    parser.add_argument("--job-status", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = build_proof(
        repo=args.repo,
        base=args.base,
        candidate=args.candidate,
        module=args.module,
        canonical=args.canonical,
        gradle_log=args.gradle_log,
        webview=args.webview == "true",
        job_status=args.job_status,
        run_id=args.run_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    main()
