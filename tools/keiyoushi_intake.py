#!/usr/bin/env python3
"""Classify Keiyoushi changes for Miyorare Source Pack intake.

The classifier is dependency-aware: a shared runtime change only affects registered
sources that actually depend on the changed shared component. Truly global runtime
changes remain fail-closed.
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
THEME_RE = re.compile(r'\btheme\s*=\s*"([^"]+)"')
THEME_PKG_RE = re.compile(r'\bthemePkg\s*=\s*"([^"]+)"')
PROJECT_DEP_RE = re.compile(r'project\(\s*"?:([^"\)]+)"?\s*\)')
PACKAGE_RE = re.compile(r'^\s*package\s+([A-Za-z0-9_.]+)', re.MULTILINE)
DECL_RE = re.compile(r'^\s*(?:class|object|interface|fun)\s+([A-Za-z_][A-Za-z0-9_]*)', re.MULTILINE)

GLOBAL_SHARED_PREFIXES = ("common/", "compiler/", "gradle/", "build-logic/", "buildSrc/")
SHARED_EXACT_PATHS = {"build.gradle.kts", "settings.gradle.kts", "gradle.properties"}
METADATA_PATH_PARTS = ("/res/mipmap-", "/res/drawable")


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
            ["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT, timeout=120
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        fail(f"git {' '.join(args)} failed in {repo}: {exc}")


def ensure_commit(repo: Path, commit: str) -> None:
    if not HEX40.fullmatch(commit):
        fail(f"invalid git SHA: {commit!r}")
    try:
        subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        try:
            subprocess.run(
                ["git", "-C", str(repo), "fetch", "--no-tags", "origin", commit],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=120,
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


def git_show(repo: Path, commit: str, path: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "show", f"{commit}:{path}"],
            text=True, stderr=subprocess.DEVNULL, timeout=60,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


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
    if "unknown" in categories:
        return "build-definition-change"
    if "semantic" in categories:
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
            removed.clear(); added.clear(); return
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
        removed.clear(); added.clear()

    for line in diff.splitlines():
        if line.startswith("@@"):
            flush()
        elif line.startswith(("---", "+++")):
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
    return (
        path in SHARED_EXACT_PATHS
        or path.startswith(GLOBAL_SHARED_PREFIXES)
        or path.startswith("core/")
        or path.startswith("lib/")
        or path.startswith("lib-multisrc/")
    )


def module_build_text(repo: Path, candidate: str, module: str) -> str:
    return git_show(repo, candidate, module.rstrip("/") + "/build.gradle.kts")


def module_themes(repo: Path, candidate: str, module: str) -> set[str]:
    text = module_build_text(repo, candidate, module)
    return set(THEME_RE.findall(text)) | set(THEME_PKG_RE.findall(text))


def module_project_dependencies(repo: Path, candidate: str, module: str) -> set[str]:
    text = module_build_text(repo, candidate, module)
    return {match.replace(":", "/").strip("/") for match in PROJECT_DEP_RE.findall(text)}


def kotlin_symbols(repo: Path, candidate: str, path: str) -> set[str]:
    text = git_show(repo, candidate, path)
    if not text:
        return set()
    package = PACKAGE_RE.search(text)
    package_name = package.group(1) if package else ""
    symbols = set(DECL_RE.findall(text))
    result = set(symbols)
    if package_name:
        result.update(f"{package_name}.{symbol}" for symbol in symbols)
    return result


def module_mentions(repo: Path, candidate: str, roots: list[str], symbols: set[str]) -> bool:
    needles = sorted({s for s in symbols if len(s) >= 4})
    if not needles:
        return False
    pattern = "|".join(re.escape(value) for value in needles)
    cmd = ["git", "-C", str(repo), "grep", "-E", "-q", pattern, candidate, "--", *roots]
    try:
        completed = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return True
    return completed.returncode == 0


def shared_path_scope(repo: Path, candidate: str, module: str, path: str) -> str:
    """Return none, dependency, or global for one shared changed path."""
    if path in SHARED_EXACT_PATHS or path.startswith(GLOBAL_SHARED_PREFIXES):
        return "global"

    if path.startswith("lib-multisrc/"):
        parts = path.split("/")
        theme = parts[1] if len(parts) > 1 else ""
        return "dependency" if theme and theme in module_themes(repo, candidate, module) else "none"

    if path.startswith("lib/"):
        parts = path.split("/")
        library = parts[1] if len(parts) > 1 else ""
        deps = module_project_dependencies(repo, candidate, module)
        return "dependency" if library and any(dep.endswith("/" + library) or dep == f"lib/{library}" for dep in deps) else "none"

    if path.startswith("core/src/main/kotlin/keiyoushi/utils/") and path.endswith(".kt"):
        themes = module_themes(repo, candidate, module)
        roots = [module] + [f"lib-multisrc/{theme}" for theme in themes]
        return "dependency" if module_mentions(repo, candidate, roots, kotlin_symbols(repo, candidate, path)) else "none"

    if path.startswith("core/"):
        return "global"
    return "none"


def relevant_shared_paths(repo: Path, candidate: str, module: str, shared_paths: list[str]) -> tuple[list[str], bool]:
    relevant: list[str] = []
    global_change = False
    for path in shared_paths:
        scope = shared_path_scope(repo, candidate, module, path)
        if scope == "global":
            global_change = True
            relevant.append(path)
        elif scope == "dependency":
            relevant.append(path)
    return relevant, global_change


def classify_module(
    repo: Path,
    base: str,
    candidate: str,
    module: str,
    paths: list[str],
    shared_changed: bool | list[str],
    *,
    global_shared_change: bool = False,
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

    if isinstance(shared_changed, bool):
        relevant_shared = ["<unknown-shared-runtime>"] if shared_changed else []
        global_shared_change = global_shared_change or shared_changed
    else:
        relevant_shared = list(shared_changed)
    if relevant_shared:
        classes.add("shared-runtime-change")

    if not own and not relevant_shared:
        state, action, automation = "unaffected", "none", "AUTO-SAFE"
    elif global_shared_change:
        state, action, automation = "review-required", "hold-unless-reusable-adapter-supports-change", "NEEDS_REVIEW"
    elif classes <= {"metadata-only", "metadata-resource-change"}:
        state, action, automation = "metadata-only", "validate-only", "AUTO-SAFE"
    elif classes <= {
        "metadata-only", "metadata-resource-change", "semantic-config-change", "literal-semantic-change"
    }:
        state, action, automation = "semantic-adapter-candidate", "adapter-required", "AUTO-REPAIRABLE"
    elif classes == {"shared-runtime-change"}:
        state, action, automation = "dependency-validation-required", "validate-dependent-runtime", "AUTO-REPAIRABLE"
    else:
        state, action, automation = "review-required", "hold-unless-reusable-adapter-supports-change", "NEEDS_REVIEW"

    return {
        "state": state,
        "action": action,
        "automationClass": automation,
        "changeClasses": sorted(classes),
        "files": details,
        "relevantSharedRuntimeFiles": relevant_shared,
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
    unsupported_classes = classes - {
        "metadata-only", "metadata-resource-change", "semantic-config-change", "literal-semantic-change"
    }
    if unsupported_classes:
        return result
    required: set[str] = set()
    if "semantic-config-change" in classes:
        required.add("domain-base-url")
    if "literal-semantic-change" in classes:
        required.add("literal-semantic")
    if not required.issubset(supported):
        return result
    out = dict(result)
    if required:
        out["state"] = "adapted"
        out["action"] = "validate-adapter-output"
        out["automationClass"] = "AUTO-REPAIRABLE"
    out["adapterCoverage"] = sorted(supported)
    return out


def analyze(alias_manifest_path: Path, repo: Path, base: str, candidate: str, adapter_report: Path | None = None) -> dict[str, Any]:
    manifest = load_json(alias_manifest_path)
    paths = changed_files(repo, base, candidate)
    shared_paths = [path for path in paths if is_shared_path(path)]
    coverage = adapter_coverage(adapter_report)

    sources = []
    for item in aliases(manifest):
        kei = item["keiyoushi"]
        official = item["official"]
        canonical = item.get("canonicalId")
        relevant, global_change = relevant_shared_paths(repo, candidate, kei["module"], shared_paths)
        result = classify_module(
            repo, base, candidate, kei["module"], paths, relevant, global_shared_change=global_change
        )
        result = apply_adapter_coverage(canonical, result, coverage)
        sources.append({
            "canonicalId": canonical,
            "pack": official.get("pack"),
            "officialSourceName": official.get("sourceName"),
            "keiyoushiModule": kei["module"],
            **result,
        })

    affected = [item for item in sources if item["state"] != "unaffected"]
    blocking = [item for item in affected if item["automationClass"] == "NEEDS_REVIEW"]
    repairable = [item for item in affected if item["automationClass"] == "AUTO-REPAIRABLE"]
    return {
        "schema": 4,
        "provider": "keiyoushi",
        "base": base,
        "candidate": candidate,
        "changedFileCount": len(paths),
        "sharedRuntimeFiles": shared_paths,
        "registeredSourceCount": len(sources),
        "affectedSourceCount": len(affected),
        "autoRepairableSourceCount": len(repairable),
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
    parser.add_argument("--strict", action="store_true", help="Exit 3 only for registered sources that still need human review")
    args = parser.parse_args()

    adapter_report = args.adapter_report.resolve() if args.adapter_report else Path("build/keiyoushi-semantic-adapter.json").resolve()
    report = analyze(
        args.aliases.resolve(), args.repo.resolve(), args.base.lower(), args.candidate.lower(), adapter_report
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict and report["state"] == "hold":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
