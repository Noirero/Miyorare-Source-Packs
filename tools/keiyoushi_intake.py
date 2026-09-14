#!/usr/bin/env python3
"""Classify Keiyoushi upstream changes for Miyorare Source Pack intake.

Keiyoushi and UMA/Tsuki use different source APIs, so Kotlin implementation changes are never treated
as automatically portable merely because both implementations represent the same website. Reusable
semantic adapters may explicitly cover narrow change classes such as domain/baseUrl migration and
literal-only parser updates. Everything structural or shared-runtime stays fail-closed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

HEX40 = re.compile(r"^[0-9a-f]{40}$")
KOTLIN_STRING_RE = re.compile(r'"((?:\\.|[^"\\])*)"')
SHARED_PREFIXES = (
    "lib-multisrc/",
    "core/",
    "gradle/",
    "build-logic/",
    "buildSrc/",
)
METADATA_PATH_PARTS = (
    "/res/mipmap-",
    "/res/drawable",
)


def fail(message: str, code: int = 1) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"could not read {path}: {exc}")
    if not isinstance(value, dict):
        fail(f"{path} must contain a JSON object")
    return value


def git(repo: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), *args],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        fail(f"git {' '.join(args)} failed in {repo}: {exc}")


def ensure_commit(repo: Path, commit: str) -> None:
    if not HEX40.fullmatch(commit):
        fail(f"invalid git SHA: {commit!r}")
    try:
        subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        try:
            subprocess.run(
                ["git", "-C", str(repo), "fetch", "--no-tags", "origin", commit],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            fail(f"could not fetch commit {commit}: {exc}")


def changed_files(repo: Path, base: str, candidate: str) -> list[str]:
    ensure_commit(repo, base)
    ensure_commit(repo, candidate)
    out = git(repo, "diff", "--name-only", f"{base}..{candidate}")
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def diff_for_path(repo: Path, base: str, candidate: str, path: str) -> str:
    return git(repo, "diff", "--unified=0", f"{base}..{candidate}", "--", path)


def aliases(alias_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw = alias_manifest.get("aliases")
    if not isinstance(raw, list):
        fail("alias manifest must contain aliases[]")
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kei = item.get("keiyoushi")
        official = item.get("official")
        if not isinstance(kei, dict) or not isinstance(official, dict):
            continue
        module = kei.get("module")
        if not isinstance(module, str) or not module:
            continue
        result.append(item)
    return result


def build_gradle_kind(diff: str) -> str:
    changed = []
    for line in diff.splitlines():
        if not line or line.startswith(("+++", "---", "@@")):
            continue
        if line[0] not in "+-":
            continue
        changed.append(line[1:].strip())
    if not changed:
        return "metadata-only"

    metadata_patterns = (
        "versionCode",
        "versionId",
        "isNsfw",
        "name =",
        "lang =",
    )
    semantic_patterns = (
        "baseUrl",
        "webUrl",
        "apiUrl",
        "sourceUrl",
        "themePkg",
    )

    if all(any(token in line for token in metadata_patterns) for line in changed):
        return "metadata-only"
    if any(any(token in line for token in semantic_patterns) for line in changed):
        return "semantic-config-change"
    return "build-definition-change"


def normalize_kotlin_line(line: str) -> str:
    return KOTLIN_STRING_RE.sub('"<STR>"', line.strip())


def kotlin_change_kind(diff: str) -> str:
    """Classify a Kotlin diff as literal-only when code structure is unchanged in every hunk."""
    removed: list[str] = []
    added: list[str] = []
    saw_literal_change = False
    unsupported = False

    def flush() -> None:
        nonlocal saw_literal_change, unsupported
        if not removed and not added:
            return
        if len(removed) != len(added):
            unsupported = True
            removed.clear()
            added.clear()
            return
        for old_line, new_line in zip(removed, added):
            old_literals = KOTLIN_STRING_RE.findall(old_line)
            new_literals = KOTLIN_STRING_RE.findall(new_line)
            if normalize_kotlin_line(old_line) != normalize_kotlin_line(new_line):
                unsupported = True
                continue
            if len(old_literals) != len(new_literals):
                unsupported = True
                continue
            if any(old != new for old, new in zip(old_literals, new_literals)):
                saw_literal_change = True
            else:
                unsupported = True
        removed.clear()
        added.clear()

    for line in diff.splitlines():
        if line.startswith("@@"):
            flush()
        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
        else:
            flush()
    flush()

    return "literal-semantic-change" if saw_literal_change and not unsupported else "parser-code-change"


def classify_module(repo: Path, base: str, candidate: str, module: str, paths: list[str], shared_changed: bool) -> dict[str, Any]:
    module_prefix = module.rstrip("/") + "/"
    own = [path for path in paths if path == module or path.startswith(module_prefix)]
    classes: set[str] = set()
    details: list[dict[str, str]] = []

    for path in own:
        if path.endswith("build.gradle.kts"):
            kind = build_gradle_kind(diff_for_path(repo, base, candidate, path))
        elif path.endswith(".kt"):
            kind = kotlin_change_kind(diff_for_path(repo, base, candidate, path))
        elif any(part in path for part in METADATA_PATH_PARTS) or path.endswith((".png", ".webp", ".jpg", ".jpeg", ".xml")):
            kind = "metadata-resource-change"
        else:
            kind = "module-resource-or-structure-change"
        classes.add(kind)
        details.append({"path": path, "class": kind})

    if shared_changed:
        classes.add("shared-runtime-change")

    if not own and not shared_changed:
        state = "unaffected"
        action = "none"
    elif classes <= {"metadata-only", "metadata-resource-change"}:
        state = "metadata-only"
        action = "validate-only"
    elif classes <= {
        "metadata-only",
        "metadata-resource-change",
        "semantic-config-change",
        "literal-semantic-change",
    }:
        state = "semantic-adapter-candidate"
        action = "adapter-required"
    else:
        state = "review-required"
        action = "hold-unless-reusable-adapter-supports-change"

    return {
        "state": state,
        "action": action,
        "changeClasses": sorted(classes),
        "files": details,
    }


def adapter_coverage(path: Path | None) -> dict[str, set[str]]:
    if path is None or not path.is_file():
        return {}
    report = load_json(path)
    result: dict[str, set[str]] = {}
    for item in report.get("applied", []):
        if not isinstance(item, dict):
            continue
        canonical = item.get("canonicalId")
        if not isinstance(canonical, str):
            continue
        change_classes = item.get("changeClasses", [])
        if isinstance(change_classes, list):
            for change_class in change_classes:
                if isinstance(change_class, str):
                    result.setdefault(canonical, set()).add(change_class)
        legacy_class = item.get("changeClass")
        if isinstance(legacy_class, str):
            result.setdefault(canonical, set()).add(legacy_class)
    return result


def apply_adapter_coverage(canonical: str | None, result: dict[str, Any], coverage: dict[str, set[str]]) -> dict[str, Any]:
    if not canonical or canonical not in coverage:
        return result
    classes = set(result.get("changeClasses", []))
    supported = coverage[canonical]

    required: set[str] = set()
    unsupported_classes = classes - {
        "metadata-only",
        "metadata-resource-change",
        "semantic-config-change",
        "literal-semantic-change",
    }
    if unsupported_classes:
        return result
    if "semantic-config-change" in classes:
        required.add("domain-base-url")
    if "literal-semantic-change" in classes:
        required.add("literal-semantic")
    if not required.issubset(supported):
        return result

    result = dict(result)
    result["state"] = "adapted" if required else result["state"]
    result["action"] = "validate-adapter-output" if required else result["action"]
    result["adapterCoverage"] = sorted(supported)
    return result


def analyze(
    alias_manifest_path: Path,
    repo: Path,
    base: str,
    candidate: str,
    adapter_report: Path | None = None,
) -> dict[str, Any]:
    manifest = load_json(alias_manifest_path)
    paths = changed_files(repo, base, candidate)
    shared_paths = [path for path in paths if path.startswith(SHARED_PREFIXES)]
    shared_changed = bool(shared_paths)
    coverage = adapter_coverage(adapter_report)

    sources = []
    for item in aliases(manifest):
        kei = item["keiyoushi"]
        official = item["official"]
        canonical = item.get("canonicalId")
        result = classify_module(repo, base, candidate, kei["module"], paths, shared_changed)
        result = apply_adapter_coverage(canonical, result, coverage)
        sources.append(
            {
                "canonicalId": canonical,
                "pack": official.get("pack"),
                "officialSourceName": official.get("sourceName"),
                "keiyoushiModule": kei["module"],
                **result,
            }
        )

    affected = [item for item in sources if item["state"] != "unaffected"]
    blocking = [item for item in affected if item["action"] in ("adapter-required", "hold-unless-reusable-adapter-supports-change")]
    return {
        "schema": 3,
        "provider": "keiyoushi",
        "base": base,
        "candidate": candidate,
        "changedFileCount": len(paths),
        "sharedRuntimeFiles": shared_paths,
        "registeredSourceCount": len(sources),
        "affectedSourceCount": len(affected),
        "blockingSourceCount": len(blocking),
        "state": "hold" if blocking else "clear",
        "sources": sources,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aliases", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--adapter-report", type=Path)
    parser.add_argument("--strict", action="store_true", help="Exit 3 when registered sources need an adapter/review")
    args = parser.parse_args()

    adapter_report = args.adapter_report.resolve() if args.adapter_report else Path("build/keiyoushi-semantic-adapter.json").resolve()
    report = analyze(
        args.aliases.resolve(),
        args.repo.resolve(),
        args.base.lower(),
        args.candidate.lower(),
        adapter_report=adapter_report,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict and report["state"] == "hold":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
