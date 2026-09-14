#!/usr/bin/env python3
"""Guard per-source runtime probes against unsafe probe targets and weak evidence.

Kotlin parsers sometimes build URLs with strings such as ``https://$domain`` while the
real host is declared through ``ConfigKey.Domain``. Such runtime expressions must never
accumulate hard-failure counts. This guard resolves a static ConfigKey.Domain host when
possible; otherwise it resets the source to UNKNOWN/no-probe-target.

A root-level HTTP probe is also only a reachability signal. Even after repeated failures,
it may not declare a source BROKEN by itself because CDN policy, geo blocking, DNS, or a
GitHub-hosted runner can differ from real app runtime. Network-only failures stay DEGRADED
until a stronger parser/runtime check confirms the source is broken.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

STATIC_HOST_RE = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
CONFIG_DOMAIN_RE = re.compile(r'ConfigKey\.Domain\(\s*"([A-Za-z0-9.-]+\.[A-Za-z]{2,63})"')


def load_runtime_module():
    path = Path(__file__).with_name("source_runtime.py")
    spec = importlib.util.spec_from_file_location("source_runtime_guarded", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def is_static_host(host: Any) -> bool:
    if not isinstance(host, str):
        return False
    host = host.strip().lower().rstrip(".")
    if not host or any(token in host for token in ("$", "{", "}", "<", ">", " ", "/")):
        return False
    return bool(STATIC_HOST_RE.fullmatch(host))


def provider_root(args: argparse.Namespace, provider: str) -> Path | None:
    return {
        "uma": args.uma_root,
        "gekkoushi": args.gekkoushi_root,
        "keiyoushi": args.keiyoushi_root,
    }.get(provider)


def resolve_from_source(root: Path | None, relative_path: str | None) -> str | None:
    if root is None or not isinstance(relative_path, str):
        return None
    path = root / relative_path
    if not path.is_file():
        # Keiyoushi entries point to a module directory; its static domain is in build.gradle.kts.
        build = path / "build.gradle.kts"
        path = build if build.is_file() else path
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    match = CONFIG_DOMAIN_RE.search(text)
    if match:
        return match.group(1).lower().rstrip(".")
    return None


def downgrade_unconfirmed_network_breaks(state: dict[str, Any]) -> list[str]:
    """Keep root/network-only failures at DEGRADED until runtime evidence confirms BROKEN."""
    downgraded: list[str] = []
    for key, source in state.get("sources", {}).items():
        if source.get("runtimeHealth") != "BROKEN":
            continue
        if source.get("runtimeConfirmedBroken") is True:
            continue
        if source.get("probeOutcome") != "hard-failure":
            continue
        source["runtimeHealth"] = "DEGRADED"
        source["recoveryState"] = "AWAITING_RUNTIME_CONFIRMATION"
        source["networkFailureStreak"] = int(source.get("consecutiveFailures", 0) or 0)
        downgraded.append(key)
    return downgraded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-health", type=Path, required=True)
    parser.add_argument("--provider-summary", type=Path, required=True)
    parser.add_argument("--recovery-queue", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--uma-root", type=Path, required=True)
    parser.add_argument("--gekkoushi-root", type=Path, required=True)
    parser.add_argument("--keiyoushi-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--fail-threshold", type=int, default=3)
    args = parser.parse_args()

    runtime = load_runtime_module()
    state = load_json(args.source_health)
    status = load_json(args.status)
    corrections: list[dict[str, Any]] = []

    for key, source in state.get("sources", {}).items():
        host = source.get("probeHost")
        if is_static_host(host):
            continue

        resolved = resolve_from_source(
            provider_root(args, str(source.get("provider"))),
            source.get("path"),
        )
        if resolved and is_static_host(resolved):
            old = host
            source["probeHost"] = resolved
            # Undo any failure caused solely by the invalid dynamic target, then probe the real host once.
            if source.get("probeOutcome") == "hard-failure":
                source["consecutiveFailures"] = max(0, int(source.get("consecutiveFailures", 0)) - 1)
                if source.get("runtimeHealth") in {"DEGRADED", "BROKEN"} and source["consecutiveFailures"] == 0:
                    source["runtimeHealth"] = "UNKNOWN"
                    source["recoveryState"] = "IDLE"
            result = runtime.http_probe(resolved, args.timeout)
            runtime.apply_probe_result(source, result, max(1, args.fail_threshold))
            corrections.append({"sourceKey": key, "oldHost": old, "newHost": resolved, "action": "reprobe-static-domain"})
            continue

        # Never let an invalid/dynamic target progress toward BROKEN.
        source["probeHost"] = None
        source["runtimeHealth"] = "UNKNOWN"
        source["consecutiveFailures"] = 0
        source["recoveryState"] = "IDLE"
        source["probeOutcome"] = "no-probe-target"
        source.pop("lastProbe", None)
        corrections.append({"sourceKey": key, "oldHost": host, "newHost": None, "action": "quarantine-invalid-probe-target"})

    downgraded = downgrade_unconfirmed_network_breaks(state)
    summary = runtime.provider_summary(state)
    queue = runtime.build_recovery_queue(state, status)
    runtime.validate_state(state, queue)
    save_json(args.source_health, state)
    save_json(args.provider_summary, summary)
    save_json(args.recovery_queue, queue)
    print(json.dumps({
        "schema": 1,
        "corrections": corrections,
        "networkOnlyBrokenDowngraded": downgraded,
        "providerSummary": summary,
    }, indent=2))


if __name__ == "__main__":
    main()
