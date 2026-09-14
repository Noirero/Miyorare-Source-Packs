#!/usr/bin/env python3
"""Apply conservative cross-runtime semantic adaptations from Keiyoushi to Miyorare/UMA.

Supported reusable adapters are intentionally narrow:

- ``domain-base-url``: migrate a registered canonical source to Keiyoushi's candidate baseUrl.
- ``literal-semantic``: propagate a string-literal change only when the Keiyoushi code structure is
  otherwise unchanged and the old literal maps uniquely to the corresponding UMA source.

The tool modifies disposable CI/release checkouts only. It never copies arbitrary KeiSource Kotlin
into Tsuki code. Structural parser changes, shared-runtime changes, ambiguous literals, and protected
identity values remain fail-closed. Adaptations are transactional per source: neither its UMA file nor
its temporary canonical-domain metadata is written when any required adaptation for that source blocks.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse

BASE_URL_RE = re.compile(r'(?m)^\s*baseUrl\s*=\s*"([^"]+)"')
KOTLIN_STRING_RE = re.compile(r'"((?:\\.|[^"\\])*)"')
HOST_RE = re.compile(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PROVENANCE_FILE = "miyorare-semantic-adapter.json"


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
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
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
        fail(f"could not fetch Keiyoushi commit {commit}: {exc}")


def host(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        fail(f"invalid URL/domain: {value!r}")
    return hostname


def keiyoushi_module_host(repo: Path, module: str) -> str:
    build = repo / module / "build.gradle.kts"
    if not build.is_file():
        fail(f"Keiyoushi module build file missing: {build}")
    match = BASE_URL_RE.search(build.read_text(encoding="utf-8"))
    if match is None:
        fail(f"could not parse baseUrl from {build}")
    return host(match.group(1))


def literal_replacements(text: str, old_host: str, new_host: str) -> tuple[str, int]:
    if old_host == new_host:
        return text, 0
    replacements = (
        (f'"{old_host}"', f'"{new_host}"'),
        (f'"https://{old_host}"', f'"https://{new_host}"'),
        (f'"http://{old_host}"', f'"http://{new_host}"'),
    )
    total = 0
    updated = text
    for old, new in replacements:
        count = updated.count(old)
        if count:
            updated = updated.replace(old, new)
            total += count
    return updated, total


def normalize_kotlin_line(line: str) -> str:
    return KOTLIN_STRING_RE.sub('"<STR>"', line.strip())


def changed_module_kotlin_files(repo: Path, base: str, candidate: str, module: str) -> list[str]:
    ensure_commit(repo, base)
    ensure_commit(repo, candidate)
    out = git(repo, "diff", "--name-only", f"{base}..{candidate}", "--", module)
    return sorted(
        path
        for path in {line.strip() for line in out.splitlines() if line.strip()}
        if path.endswith(".kt")
    )


def changed_literal_pairs(diff: str) -> tuple[list[tuple[str, str]], bool]:
    """Return structurally identical old/new literal pairs plus an unsupported-structure flag."""
    pairs: list[tuple[str, str]] = []
    unsupported = False
    removed: list[str] = []
    added: list[str] = []

    def flush() -> None:
        nonlocal unsupported
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
            changed = False
            for old, new in zip(old_literals, new_literals):
                if old != new:
                    pairs.append((old, new))
                    changed = True
            if not changed:
                unsupported = True
        removed.clear()
        added.clear()

    for line in diff.splitlines():
        if line.startswith("@@"):
            flush()
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            removed.append(line[1:])
            continue
        if line.startswith("+"):
            added.append(line[1:])
            continue
        flush()
    flush()
    return pairs, unsupported


def literal_kind(value: str) -> str | None:
    if len(value) < 3:
        return None
    lower = value.lower()
    if lower in {"get", "post", "put", "delete", "id", "en", "all", "true", "false", "null"}:
        return None
    if value.startswith(("http://", "https://")):
        return "url"
    if HOST_RE.fullmatch(value):
        return "host"
    if value.startswith(("/", "?")) or ("/" in value and not value.isspace()):
        return "endpoint-or-path"
    if (
        value.startswith(("#", ".", "["))
        or any(token in value for token in (" > ", ":nth-", ":has(", ":contains(", "[", "]"))
    ):
        return "selector"
    if any(token in lower for token in (";q=", "application/", "text/html", "image/", "accept-language", "user-agent", "referer")):
        return "header-or-media-value"
    return None


def protected_literals(alias: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("canonicalId", "language", "verifiedDomain"):
        value = alias.get(key)
        if isinstance(value, str):
            values.add(value)
    for section in ("official", "uma", "keiyoushi"):
        meta = alias.get(section)
        if not isinstance(meta, dict):
            continue
        for key in ("pluginId", "sourceName"):
            value = meta.get(key)
            if isinstance(value, str):
                values.add(value)
    return values


def apply_literal_pair(text: str, old: str, new: str, protected: set[str]) -> tuple[str, dict[str, Any] | None, str | None]:
    old_kind = literal_kind(old)
    new_kind = literal_kind(new)
    if old_kind is None or new_kind is None:
        return text, None, "unsupported-or-too-generic-literal"
    if old_kind != new_kind:
        return text, None, f"literal-kind-changed:{old_kind}-to-{new_kind}"
    if old in protected or new in protected:
        return text, None, "protected-identity-literal"

    old_token = f'"{old}"'
    new_token = f'"{new}"'
    old_count = text.count(old_token)
    new_count = text.count(new_token)

    if old_count == 0 and new_count >= 1:
        return text, {
            "oldLiteral": old,
            "newLiteral": new,
            "kind": old_kind,
            "mode": "already-compatible",
            "replacementCount": 0,
        }, None
    if old_count != 1:
        return text, None, f"old-literal-occurrence-count-{old_count}"
    if new_count > 0:
        return text, None, "old-and-new-literals-both-present"

    return text.replace(old_token, new_token, 1), {
        "oldLiteral": old,
        "newLiteral": new,
        "kind": old_kind,
        "mode": "unique-literal-rewrite",
        "replacementCount": 1,
    }, None


def apply_semantic_adapters(
    aliases_path: Path,
    keiyoushi_root: Path,
    uma_root: Path,
    output: Path | None = None,
    base: str | None = None,
    candidate: str | None = None,
    capabilities: set[str] | None = None,
) -> dict[str, Any]:
    manifest = load_json(aliases_path)
    raw_aliases = manifest.get("aliases")
    if not isinstance(raw_aliases, list):
        fail("alias manifest must contain aliases[]")

    enabled = capabilities or {"domain-base-url"}
    if base and candidate and "literal-semantic" in enabled:
        ensure_commit(keiyoushi_root, base)
        ensure_commit(keiyoushi_root, candidate)

    applied: list[dict[str, Any]] = []
    unchanged: list[str] = []
    blocked: list[dict[str, Any]] = []

    for item in raw_aliases:
        if not isinstance(item, dict):
            continue
        canonical = item.get("canonicalId")
        verified = item.get("verifiedDomain")
        kei = item.get("keiyoushi")
        uma = item.get("uma")
        if not isinstance(canonical, str) or not isinstance(verified, str):
            continue
        if not isinstance(kei, dict) or not isinstance(uma, dict):
            continue
        module = kei.get("module")
        uma_file = uma.get("file")
        if not isinstance(module, str) or not isinstance(uma_file, str):
            continue

        target = uma_root / uma_file
        if not target.is_file():
            blocked.append(
                {
                    "canonicalId": canonical,
                    "module": module,
                    "umaFile": uma_file,
                    "reason": "uma-source-file-missing",
                }
            )
            continue

        original_text = target.read_text(encoding="utf-8")
        text = original_text
        pending_verified_domain: str | None = None
        covered_domain_pair: tuple[str, str] | None = None
        changes: list[dict[str, Any]] = []
        change_classes: set[str] = set()
        source_blocked = False

        if "domain-base-url" in enabled:
            old_host = host(verified)
            try:
                new_host = keiyoushi_module_host(keiyoushi_root, module)
            except SystemExit as exc:
                blocked.append(
                    {
                        "canonicalId": canonical,
                        "module": module,
                        "oldHost": old_host,
                        "reason": f"keiyoushi-base-url-unavailable:{exc.code}",
                    }
                )
                continue

            if new_host != old_host:
                covered_domain_pair = (old_host, new_host)
                if any(token in text for token in (f'"{new_host}"', f'"https://{new_host}"', f'"http://{new_host}"')):
                    replacement_count = 0
                    mode = "already-compatible"
                else:
                    text, replacement_count = literal_replacements(text, old_host, new_host)
                    if replacement_count == 0:
                        blocked.append(
                            {
                                "canonicalId": canonical,
                                "module": module,
                                "umaFile": uma_file,
                                "oldHost": old_host,
                                "newHost": new_host,
                                "reason": "old-verified-host-not-found-as-safe-uma-literal",
                            }
                        )
                        source_blocked = True
                    else:
                        mode = "literal-host-rewrite"
                if not source_blocked:
                    pending_verified_domain = new_host
                    change_classes.add("domain-base-url")
                    changes.append(
                        {
                            "changeClass": "domain-base-url",
                            "oldHost": old_host,
                            "newHost": new_host,
                            "mode": mode,
                            "replacementCount": replacement_count,
                        }
                    )

        if source_blocked:
            continue

        if base and candidate and base != candidate and "literal-semantic" in enabled:
            module_pairs: list[tuple[str, str, str]] = []
            for path in changed_module_kotlin_files(keiyoushi_root, base, candidate, module):
                diff = git(keiyoushi_root, "diff", "--unified=0", f"{base}..{candidate}", "--", path)
                pairs, _ = changed_literal_pairs(diff)
                for old, new in pairs:
                    module_pairs.append((old, new, path))

            seen_pairs: set[tuple[str, str]] = set()
            for old, new, path in module_pairs:
                pair_key = (old, new)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # A direct host literal matching the baseUrl migration was already handled atomically by
                # domain-base-url. Do not reject the same proven migration again as protected identity.
                if covered_domain_pair == pair_key:
                    continue

                updated, detail, reason = apply_literal_pair(text, old, new, protected_literals(item))
                if reason:
                    blocked.append(
                        {
                            "canonicalId": canonical,
                            "module": module,
                            "umaFile": uma_file,
                            "keiyoushiFile": path,
                            "oldLiteral": old,
                            "newLiteral": new,
                            "reason": reason,
                        }
                    )
                    source_blocked = True
                    break
                assert detail is not None
                text = updated
                detail["changeClass"] = "literal-semantic"
                detail["keiyoushiFile"] = path
                changes.append(detail)
                change_classes.add("literal-semantic")

        if source_blocked:
            # Transactional per source: discard every pending change for this source.
            continue

        if text != original_text:
            target.write_text(text, encoding="utf-8")
        if pending_verified_domain is not None:
            item["verifiedDomain"] = pending_verified_domain

        if changes:
            applied.append(
                {
                    "canonicalId": canonical,
                    "module": module,
                    "umaFile": uma_file,
                    "changeClasses": sorted(change_classes),
                    "changes": changes,
                }
            )
        else:
            unchanged.append(canonical)

    if applied:
        save_json(aliases_path, manifest)

    report = {
        "schema": 2,
        "adapter": "keiyoushi-semantic",
        "capabilities": sorted(enabled),
        "base": base,
        "candidate": candidate,
        "applied": applied,
        "appliedCanonicalIds": [item["canonicalId"] for item in applied],
        "unchangedCanonicalIds": unchanged,
        "blocked": blocked,
        "state": "blocked" if blocked else "clear",
    }

    save_json(uma_root / PROVENANCE_FILE, report)
    if output:
        save_json(output, report)
    return report


def apply_domain_adapters(
    aliases_path: Path,
    keiyoushi_root: Path,
    uma_root: Path,
    output: Path | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper retained for unit tests/callers during staged migration."""
    return apply_semantic_adapters(
        aliases_path=aliases_path,
        keiyoushi_root=keiyoushi_root,
        uma_root=uma_root,
        output=output,
        capabilities={"domain-base-url"},
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aliases", type=Path, required=True)
    parser.add_argument("--keiyoushi-root", type=Path, required=True)
    parser.add_argument("--uma-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base")
    parser.add_argument("--candidate")
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    capabilities = set(args.capability) if args.capability else {"domain-base-url"}
    report = apply_semantic_adapters(
        args.aliases.resolve(),
        args.keiyoushi_root.resolve(),
        args.uma_root.resolve(),
        args.output.resolve(),
        base=args.base.lower() if args.base else None,
        candidate=args.candidate.lower() if args.candidate else None,
        capabilities=capabilities,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict and report["state"] == "blocked":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
