#!/usr/bin/env python3
"""Apply conservative cross-runtime semantic adaptations from Keiyoushi to Miyorare/UMA.

The first reusable adapter intentionally handles only a deterministic change class: a canonical
source's website host/baseUrl changed upstream. It updates the temporary Miyorare alias manifest and
the temporary UMA checkout used by CI/release. It never commits upstream code and never attempts to
transpile arbitrary KeiSource Kotlin into Tsuki code.

A domain adaptation is allowed only when the registered UMA source still contains the old verified
host (or already contains the new host). Anything ambiguous is blocked so CI keeps the last-known-good
source instead of guessing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse

BASE_URL_RE = re.compile(r'(?m)^\s*baseUrl\s*=\s*"([^"]+)"')


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
    text = build.read_text(encoding="utf-8")
    match = BASE_URL_RE.search(text)
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


def apply_domain_adapters(
    aliases_path: Path,
    keiyoushi_root: Path,
    uma_root: Path,
    output: Path | None = None,
) -> dict[str, Any]:
    manifest = load_json(aliases_path)
    raw_aliases = manifest.get("aliases")
    if not isinstance(raw_aliases, list):
        fail("alias manifest must contain aliases[]")

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

        if new_host == old_host:
            unchanged.append(canonical)
            continue

        target = uma_root / uma_file
        if not target.is_file():
            blocked.append(
                {
                    "canonicalId": canonical,
                    "module": module,
                    "umaFile": uma_file,
                    "oldHost": old_host,
                    "newHost": new_host,
                    "reason": "uma-source-file-missing",
                }
            )
            continue

        original = target.read_text(encoding="utf-8")
        if any(token in original for token in (f'"{new_host}"', f'"https://{new_host}"', f'"http://{new_host}"')):
            updated = original
            replacement_count = 0
            mode = "already-compatible"
        else:
            updated, replacement_count = literal_replacements(original, old_host, new_host)
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
                continue
            mode = "literal-host-rewrite"

        if updated != original:
            target.write_text(updated, encoding="utf-8")
        item["verifiedDomain"] = new_host
        applied.append(
            {
                "canonicalId": canonical,
                "module": module,
                "umaFile": uma_file,
                "oldHost": old_host,
                "newHost": new_host,
                "mode": mode,
                "replacementCount": replacement_count,
                "changeClass": "domain-base-url",
            }
        )

    if applied:
        save_json(aliases_path, manifest)

    report = {
        "schema": 1,
        "adapter": "keiyoushi-domain-base-url",
        "applied": applied,
        "appliedCanonicalIds": [item["canonicalId"] for item in applied],
        "unchangedCanonicalIds": unchanged,
        "blocked": blocked,
        "state": "blocked" if blocked else "clear",
    }
    if output:
        save_json(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aliases", type=Path, required=True)
    parser.add_argument("--keiyoushi-root", type=Path, required=True)
    parser.add_argument("--uma-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = apply_domain_adapters(
        args.aliases.resolve(),
        args.keiyoushi_root.resolve(),
        args.uma_root.resolve(),
        args.output.resolve(),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict and report["state"] == "blocked":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
