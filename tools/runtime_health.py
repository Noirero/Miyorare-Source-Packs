#!/usr/bin/env python3
"""Persistent runtime-health state for Miyorare Source Packs.

Update state and runtime health are independent. The upstream-sync workflow may rewrite
``upstream/status.json``; runtime health is therefore persisted separately in
``upstream/runtime-health.json`` and reconciled back into status after each sync run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn

HEX40 = re.compile(r"^[0-9a-f]{40}$")
UPDATE_STATES = {"CANDIDATE", "PROMOTED", "HELD"}
RUNTIME_HEALTH = {"HEALTHY", "DEGRADED", "BROKEN", "UNKNOWN"}
RECOVERY_STATES = {
    "IDLE",
    "ADAPTING_LATEST",
    "TRY_PREVIOUS_HEALTHY",
    "TRY_CANONICAL_FALLBACK",
    "TEMPORARILY_UNAVAILABLE",
}
REQUIRED_PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
DEFAULT_HISTORY_LIMIT = 5


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


def unique_commits(values: list[str], limit: int = DEFAULT_HISTORY_LIMIT) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and HEX40.fullmatch(value) and value not in result:
            result.append(value)
    return result[: max(1, limit)]


def history_limit(provider: dict[str, Any]) -> int:
    raw = provider.get("healthyHistoryLimit", DEFAULT_HISTORY_LIMIT)
    return raw if isinstance(raw, int) and raw > 0 else DEFAULT_HISTORY_LIMIT


def legacy_update_state(current: dict[str, Any]) -> str:
    update_state = current.get("updateState")
    if isinstance(update_state, str) and update_state.upper() in UPDATE_STATES:
        return update_state.upper()
    legacy = str(current.get("state", "promoted")).lower()
    if legacy == "held":
        return "HELD"
    if legacy == "candidate":
        return "CANDIDATE"
    return "PROMOTED"


def initialize_health_store(registry: dict[str, Any], store: dict[str, Any] | None = None) -> dict[str, Any]:
    providers = registry.get("providers")
    if not isinstance(providers, dict):
        fail("registry.providers is required")
    raw_store = store.get("providers", {}) if isinstance(store, dict) else {}
    out: dict[str, Any] = {"schema": 1, "providers": {}}
    for name in REQUIRED_PROVIDERS:
        cfg = providers.get(name)
        if not isinstance(cfg, dict):
            fail(f"registry provider missing: {name}")
        previous = raw_store.get(name) if isinstance(raw_store, dict) else None
        previous = previous if isinstance(previous, dict) else {}
        cfg_lkg = cfg["lastKnownGood"]
        previous_active = previous.get("activeCommit")
        active_changed = isinstance(previous_active, str) and previous_active != cfg_lkg
        runtime_health = str(previous.get("runtimeHealth", "UNKNOWN")).upper()
        if runtime_health not in RUNTIME_HEALTH or active_changed:
            runtime_health = "UNKNOWN"
        recovery = str(previous.get("recoveryState", "IDLE")).upper()
        if recovery not in RECOVERY_STATES or active_changed:
            recovery = "IDLE"
        history = unique_commits(
            [*previous.get("healthyHistory", []), *cfg.get("healthyHistory", []), cfg_lkg],
            history_limit(cfg),
        )
        entry = dict(previous)
        entry.update({
            "runtimeHealth": runtime_health,
            "activeCommit": cfg_lkg,
            "healthyHistory": history,
            "recoveryState": recovery,
        })
        out["providers"][name] = entry
    return out


def sync_status(registry: dict[str, Any], status: dict[str, Any], health_store: dict[str, Any]) -> dict[str, Any]:
    providers = registry["providers"]
    current_providers = status.get("providers") if isinstance(status.get("providers"), dict) else {}
    health_providers = health_store["providers"]
    out: dict[str, Any] = {"schema": 3, "providers": {}}
    for name in REQUIRED_PROVIDERS:
        cfg = providers[name]
        current = current_providers.get(name) if isinstance(current_providers, dict) else None
        current = dict(current) if isinstance(current, dict) else {}
        health = health_providers[name]
        entry = dict(current)
        entry.pop("state", None)
        entry.update({
            "updateState": legacy_update_state(current),
            "runtimeHealth": health["runtimeHealth"],
            "activeCommit": health["activeCommit"],
            "lastKnownGood": cfg["lastKnownGood"],
            "healthyHistory": list(health["healthyHistory"]),
            "recoveryState": health["recoveryState"],
        })
        out["providers"][name] = entry
    return out


def reconcile_registry_history(registry: dict[str, Any], health_store: dict[str, Any]) -> None:
    for name in REQUIRED_PROVIDERS:
        cfg = registry["providers"][name]
        store = health_store["providers"][name]
        cfg["healthyHistory"] = unique_commits(
            [*store.get("healthyHistory", []), *cfg.get("healthyHistory", [])], history_limit(cfg)
        )


def mark_health(status: dict[str, Any], health_store: dict[str, Any], provider_name: str, health: str, reason: str | None = None) -> None:
    provider = status["providers"].get(provider_name)
    stored = health_store["providers"].get(provider_name)
    if not isinstance(provider, dict) or not isinstance(stored, dict):
        fail(f"unknown provider {provider_name}")
    health = health.upper()
    if health not in RUNTIME_HEALTH:
        fail(f"unsupported runtime health: {health}")
    for target in (provider, stored):
        target["runtimeHealth"] = health
        if reason:
            target["reason"] = reason
        elif health == "HEALTHY":
            target.pop("reason", None)
    if health == "HEALTHY":
        for target in (provider, stored):
            target["recoveryState"] = "IDLE"
            active = target.get("activeCommit")
            target["healthyHistory"] = unique_commits([active, *target.get("healthyHistory", [])])
    elif health == "BROKEN":
        recovery = "ADAPTING_LATEST" if provider.get("candidate") else "TRY_PREVIOUS_HEALTHY"
        provider["recoveryState"] = recovery
        stored["recoveryState"] = recovery


def hold_candidate(status: dict[str, Any], provider_name: str, candidate: str, reason: str) -> None:
    if not HEX40.fullmatch(candidate):
        fail("candidate must be a 40-character git SHA")
    provider = status["providers"].get(provider_name)
    if not isinstance(provider, dict):
        fail(f"unknown provider {provider_name}")
    provider["updateState"] = "HELD"
    provider["candidate"] = candidate
    provider["reason"] = reason
    if provider.get("runtimeHealth") == "BROKEN":
        provider["recoveryState"] = "ADAPTING_LATEST"


def promote_candidate(registry: dict[str, Any], status: dict[str, Any], health_store: dict[str, Any], provider_name: str, commit: str) -> None:
    if not HEX40.fullmatch(commit):
        fail("promotion commit must be a 40-character git SHA")
    cfg = registry.get("providers", {}).get(provider_name)
    provider = status.get("providers", {}).get(provider_name)
    stored = health_store.get("providers", {}).get(provider_name)
    if not isinstance(cfg, dict) or not isinstance(provider, dict) or not isinstance(stored, dict):
        fail(f"unknown provider {provider_name}")
    cfg["upstreamBase"] = commit
    cfg["lastKnownGood"] = commit
    provider.update({
        "updateState": "PROMOTED",
        "activeCommit": commit,
        "lastKnownGood": commit,
        "candidate": commit,
        "runtimeHealth": "UNKNOWN",
        "recoveryState": "IDLE",
    })
    stored.update({"activeCommit": commit, "runtimeHealth": "UNKNOWN", "recoveryState": "IDLE"})


def recovery_plan(registry: dict[str, Any], status: dict[str, Any], provider_name: str) -> dict[str, Any]:
    cfg = registry.get("providers", {}).get(provider_name)
    provider = status.get("providers", {}).get(provider_name)
    if not isinstance(cfg, dict) or not isinstance(provider, dict):
        fail(f"unknown provider {provider_name}")
    if provider.get("runtimeHealth") != "BROKEN":
        return {"provider": provider_name, "action": "NONE", "reason": "active-runtime-not-broken"}
    candidate = provider.get("candidate")
    active = provider.get("activeCommit")
    if isinstance(candidate, str) and HEX40.fullmatch(candidate) and candidate != active:
        return {"provider": provider_name, "action": "ADAPT_LATEST", "commit": candidate}
    history = unique_commits(provider.get("healthyHistory", []) + cfg.get("healthyHistory", []))
    previous = next((sha for sha in history if sha != active), None)
    if previous:
        return {"provider": provider_name, "action": "TRY_PREVIOUS_HEALTHY", "commit": previous}
    if registry.get("policy", {}).get("validatedCanonicalFallback") is True:
        return {"provider": provider_name, "action": "TRY_CANONICAL_FALLBACK"}
    return {"provider": provider_name, "action": "TEMPORARILY_UNAVAILABLE"}


def validate(registry: dict[str, Any], status: dict[str, Any], health_store: dict[str, Any]) -> None:
    policy = registry.get("policy")
    if not isinstance(policy, dict):
        fail("registry.policy is required")
    for key in (
        "autoAdaptUntilCompatible",
        "retryLatestCandidateOnFailure",
        "separateRuntimeHealth",
        "maintainHealthyHistory",
        "emergencyAutoRepair",
        "validatedCanonicalFallback",
        "temporarilyUnavailableOnNoHealthyOption",
        "perSourceIsolation",
        "latestCandidateWinsOnRetry",
    ):
        if policy.get(key) is not True:
            fail(f"registry.policy.{key} must stay true")
    for name in REQUIRED_PROVIDERS:
        provider = status["providers"][name]
        stored = health_store["providers"][name]
        if provider["updateState"] not in UPDATE_STATES:
            fail(f"invalid update state for {name}")
        if provider["runtimeHealth"] not in RUNTIME_HEALTH:
            fail(f"invalid runtime health for {name}")
        if stored["runtimeHealth"] not in RUNTIME_HEALTH:
            fail(f"invalid persistent runtime health for {name}")
        if provider["recoveryState"] not in RECOVERY_STATES:
            fail(f"invalid recovery state for {name}")
        if not stored["healthyHistory"]:
            fail(f"healthy history must not be empty for {name}")


def load_state(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry = load_json(args.registry.resolve())
    raw_status = load_json(args.status.resolve())
    health_path = args.health_store.resolve()
    raw_health = load_json(health_path) if health_path.is_file() else {"schema": 1, "providers": {}}
    health_store = initialize_health_store(registry, raw_health)
    status = sync_status(registry, raw_status, health_store)
    return registry, status, health_store


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--health-store", type=Path, required=True)


def save_state(args: argparse.Namespace, registry: dict[str, Any], status: dict[str, Any], health_store: dict[str, Any]) -> None:
    reconcile_registry_history(registry, health_store)
    save_json(args.registry.resolve(), registry)
    save_json(args.status.resolve(), status)
    save_json(args.health_store.resolve(), health_store)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_sync = sub.add_parser("sync"); add_common(p_sync)
    p_validate = sub.add_parser("validate"); add_common(p_validate)
    p_health = sub.add_parser("health"); add_common(p_health); p_health.add_argument("--provider", required=True); p_health.add_argument("--health", required=True); p_health.add_argument("--reason")
    p_hold = sub.add_parser("hold"); add_common(p_hold); p_hold.add_argument("--provider", required=True); p_hold.add_argument("--candidate", required=True); p_hold.add_argument("--reason", required=True)
    p_promote = sub.add_parser("promote"); add_common(p_promote); p_promote.add_argument("--provider", required=True); p_promote.add_argument("--commit", required=True)
    p_recovery = sub.add_parser("recovery-plan"); add_common(p_recovery); p_recovery.add_argument("--provider", required=True)
    args = parser.parse_args()
    registry, status, health_store = load_state(args)

    if args.command == "sync":
        save_state(args, registry, status, health_store)
    elif args.command == "validate":
        validate(registry, status, health_store)
        print("runtime health state is valid")
    elif args.command == "health":
        mark_health(status, health_store, args.provider, args.health, args.reason)
        save_state(args, registry, status, health_store)
    elif args.command == "hold":
        hold_candidate(status, args.provider, args.candidate.lower(), args.reason)
        save_state(args, registry, status, health_store)
    elif args.command == "promote":
        promote_candidate(registry, status, health_store, args.provider, args.commit.lower())
        save_state(args, registry, status, health_store)
    elif args.command == "recovery-plan":
        print(json.dumps(recovery_plan(registry, status, args.provider), indent=2))
    else:
        fail(f"unsupported command {args.command}")


if __name__ == "__main__":
    main()
