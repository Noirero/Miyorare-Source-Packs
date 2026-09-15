#!/usr/bin/env python3
"""Dependency-aware Keiyoushi intake classifier for Miyorare Source Packs.

The classifier is fail-closed, but no longer treats every Keiyoushi shared-runtime edit as a change to
every registered Miyorare source. Shared changes are associated with a source only when its module
references the affected runtime/multisrc symbol. Known cross-runtime structural migrations may be
accepted only when a deterministic structural adapter has produced audited provenance.
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
    "common/",
    "compiler/",
    "core/",
    "gradle/",
    "build-logic/",
    "buildSrc/",
)
SHARED_EXACT_PATHS = {
    "build.gradle.kts",
    "settings.gradle.kts",
    "gradle.properties",
}
METADATA_PATH_PARTS = (
    "/res/mipmap-",
    "/res/drawable",
)
BASE_ALLOWED_CLASSES = {
    "metadata-only",
    "metadata-resource-change",
    "semantic-config-change",
    "literal-semantic-change",
}
STRUCTURAL_CLASSES = {
    "build-definition-change",
    "parser-code-change",
    "module-resource-or-structure-change",
    "shared-runtime-change",
}


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


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
    probe = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode == 0:
        return
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
        if isinstance(module, str) and module:
            result.append(item)
    return result


def changed_diff_lines(diff: str) -> list[str]:
    changed: list[str] = []
    for line in diff.splitlines():
        if not line or line.startswith(("+++", "---", "@@")):
            continue
        if line[0] in "+-":
            changed.append(line[1:].strip())
    return changed


def build_gradle_kind(diff: str) -> str:
    changed = changed_diff_lines(diff)
    if not changed:
        return "metadata-only"

    metadata_patterns = ("versionCode", "versionId", "isNsfw", "name =", "lang =")
    semantic_patterns = ("baseUrl", "webUrl", "apiUrl", "sourceUrl", "themePkg")

    def category(line: str) -> str:
        if any(token in line for token in metadata_patterns):
            return "metadata"
        if any(token in line for token in semantic_patterns):
            return "semantic"
        return "unknown"

    categories = [category(line) for line in changed]
    if any(kind == "unknown" for kind in categories):
        return "build-definition-change"
    if any(kind == "semantic" for kind in categories):
        return "semantic-config-change"
    return "metadata-only"


def normalize_kotlin_line(line: str) -> str:
    return KOTLIN_STRING_RE.sub('"<STR>"', line.strip())


def kotlin_change_kind(diff: str) -> str:
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


def is_shared_path(path: str) -> bool:
    return path in SHARED_EXACT_PATHS or path.startswith(SHARED_PREFIXES)


def module_text(repo: Path, module: str) -> str:
    root = repo / module
    if not root.is_dir():
        return ""
    parts: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".kt", ".kts"):
            try:
                parts.append(path.read_text(encoding="utf-8"))
            except OSError:
                continue
    return "\n".join(parts)


def shared_dependency_tokens(path: str) -> set[str]:
    parts = Path(path).parts
    tokens: set[str] = set()
    if len(parts) >= 2 and parts[0] in ("lib-multisrc", "lib"):
        name = parts[1]
        tokens.update({name, f"multisrc.{name}", f"lib.{name}"})
    stem = Path(path).stem
    if stem not in {"build", "settings", "gradle", "properties", "Dto"}:
        tokens.add(stem)
    return {token.lower() for token in tokens if token}


def relevant_shared_paths(repo: Path, module: str, shared_paths: list[str]) -> list[str]:
    if not shared_paths:
        return []
    text = module_text(repo, module).lower()
    result: list[str] = []
    for path in shared_paths:
        if path in SHARED_EXACT_PATHS:
            result.append(path)
            continue
        tokens = shared_dependency_tokens(path)
        if tokens and any(token in text for token in tokens):
            result.append(path)
    return result


def classify_module(
    repo: Path,
    base: str,
    candidate: str,
    module: str,
    paths: list[str],
    source_shared_paths: list[str],
) -> dict[str, Any]:
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

    if source_shared_paths:
        classes.add("shared-runtime-change")

    if not own and not source_shared_paths:
        state = "unaffected"
        action = "none"
    elif classes <= {"metadata-only", "metadata-resource-change"}:
        state = "metadata-only"
        action = "validate-only"
    elif classes <= BASE_ALLOWED_CLASSES:
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
        "sharedRuntimeFiles": source_shared_paths,
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
        for change_class in item.get("changeClasses", []):
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
    unknown = classes - BASE_ALLOWED_CLASSES - STRUCTURAL_CLASSES
    if unknown:
        return result

    required: set[str] = set()
    if "semantic-config-change" in classes:
        required.add("domain-base-url")
    if "literal-semantic-change" in classes:
        required.add("literal-semantic")
    if classes & STRUCTURAL_CLASSES:
        required.add("structural-profile")
    if not required.issubset(supported):
        return result

    updated = dict(result)
    if required:
        updated["state"] = "adapted"
        updated["action"] = "validate-adapter-output"
    updated["adapterCoverage"] = sorted(supported)
    return updated


def analyze(
    alias_manifest_path: Path,
    repo: Path,
    base: str,
    candidate: str,
    adapter_report: Path | None = None,
) -> dict[str, Any]:
    manifest = load_json(alias_manifest_path)
    paths = changed_files(repo, base, candidate)
    shared_paths = [path for path in paths if is_shared_path(path)]
    coverage = adapter_coverage(adapter_report)

    sources = []
    for item in aliases(manifest):
        kei = item["keiyoushi"]
        official = item["official"]
        canonical = item.get("canonicalId")
        source_shared = relevant_shared_paths(repo, kei["module"], shared_paths)
        result = classify_module(repo, base, candidate, kei["module"], paths, source_shared)
        result = apply_adapter_coverage(canonical, result, coverage)
        sources.append({
            "canonicalId": canonical,
            "pack": official.get("pack"),
            "officialSourceName": official.get("sourceName"),
            "keiyoushiModule": kei["module"],
            **result,
        })

    affected = [item for item in sources if item["state"] != "unaffected"]
    blocking = [
        item for item in affected
        if item["action"] in ("adapter-required", "hold-unless-reusable-adapter-supports-change")
    ]
    return {
        "schema": 4,
        "classifier": "dependency-aware-structural-v2",
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


def apply_structural_profile_if_available(
    aliases_path: Path,
    repo: Path,
    base: str,
    candidate: str,
    adapter_report: Path,
) -> None:
    uma_root = Path("_upstream/uma").resolve()
    if not uma_root.is_dir():
        return

    if not adapter_report.is_file():
        save_json(adapter_report, {
            "schema": 2,
            "adapter": "keiyoushi-semantic",
            "capabilities": [],
            "base": base,
            "candidate": candidate,
            "applied": [],
            "appliedCanonicalIds": [],
            "unchangedCanonicalIds": [],
            "blocked": [],
            "state": "clear",
        })

    try:
        from keiyoushi_structural_adapter import apply_structural_adapters
        report = apply_structural_adapters(
            aliases_path=aliases_path,
            keiyoushi_root=repo,
            uma_root=uma_root,
            output=adapter_report,
        )
    except (ImportError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        fail(f"structural adapter failed: {exc}", code=3)

    if report.get("state") == "blocked":
        blocked = ", ".join(
            item.get("canonicalId", "unknown")
            for item in report.get("blocked", [])
            if isinstance(item, dict)
        )
        fail(f"structural adapter blocked for: {blocked or 'unknown'}", code=3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aliases", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--adapter-report", type=Path)
    parser.add_argument("--strict", action="store_true", help="Exit 3 when registered sources still need an adapter/review")
    args = parser.parse_args()

    aliases_path = args.aliases.resolve()
    repo = args.repo.resolve()
    base = args.base.lower()
    candidate = args.candidate.lower()
    adapter_report = args.adapter_report.resolve() if args.adapter_report else Path("build/keiyoushi-semantic-adapter.json").resolve()

    apply_structural_profile_if_available(aliases_path, repo, base, candidate, adapter_report)
    report = analyze(aliases_path, repo, base, candidate, adapter_report=adapter_report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict and report["state"] == "hold":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
