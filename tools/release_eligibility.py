#!/usr/bin/env python3
"""Explicit provider release eligibility for the authoritative Compatibility Farm.

runtimeHealth describes observed runtime condition. releaseEligibility is the
separate, fail-closed decision consumed by stable Source Pack publication.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
RUNTIME_HEALTH = {"HEALTHY", "DEGRADED", "BROKEN", "UNKNOWN"}
RECOVERY_STATES = {
    "IDLE",
    "ADAPTING_LATEST",
    "TRY_PREVIOUS_HEALTHY",
    "TRY_CANONICAL_FALLBACK",
    "TEMPORARILY_UNAVAILABLE",
}
RELEASE_ELIGIBILITY = {"ELIGIBLE", "BLOCKED"}


class ReleaseEligibilityError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReleaseEligibilityError(f"{path} must contain a JSON object")
    return value


def save_json(path: str | Path, value: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def derive(provider: str, state: dict[str, Any], approved_baseline: str) -> tuple[str, str]:
    if not isinstance(approved_baseline, str) or not HEX40.fullmatch(approved_baseline):
        raise ReleaseEligibilityError(f"{provider} approved baseline must be a 40-character git SHA")
    if not isinstance(state, dict):
        raise ReleaseEligibilityError(f"{provider} status must be an object")

    active = state.get("activeCommit")
    lkg = state.get("lastKnownGood")
    if active != approved_baseline:
        return "BLOCKED", "ACTIVE_COMMIT_NOT_APPROVED_BASELINE"
    if lkg != approved_baseline:
        return "BLOCKED", "LAST_KNOWN_GOOD_NOT_APPROVED_BASELINE"

    runtime_health = state.get("runtimeHealth")
    if runtime_health not in RUNTIME_HEALTH:
        raise ReleaseEligibilityError(f"{provider} runtimeHealth is invalid: {runtime_health!r}")

    recovery_state = state.get("recoveryState")
    if recovery_state not in RECOVERY_STATES:
        raise ReleaseEligibilityError(f"{provider} recoveryState is invalid: {recovery_state!r}")

    if recovery_state == "TEMPORARILY_UNAVAILABLE":
        return "BLOCKED", "NO_HEALTHY_RUNTIME_AVAILABLE"
    if runtime_health == "BROKEN":
        return "BLOCKED", "ACTIVE_RUNTIME_BROKEN"
    if runtime_health == "UNKNOWN":
        return "BLOCKED", "RUNTIME_HEALTH_UNKNOWN"

    return "ELIGIBLE", "ACTIVE_COMMIT_IS_LAST_KNOWN_GOOD"


def _providers(status: dict[str, Any], source_registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if status.get("schema") != 3:
        raise ReleaseEligibilityError("authoritative Farm status schema must be 3")
    status_providers = status.get("providers")
    if not isinstance(status_providers, dict):
        raise ReleaseEligibilityError("authoritative Farm providers must be an object")
    baselines = source_registry.get("providerBaselines")
    if not isinstance(baselines, dict):
        raise ReleaseEligibilityError("providerBaselines must be an object")
    for provider in REQUIRED_PROVIDERS:
        if not isinstance(status_providers.get(provider), dict):
            raise ReleaseEligibilityError(f"status provider missing: {provider}")
        if provider not in baselines:
            raise ReleaseEligibilityError(f"approved provider baseline missing: {provider}")
    return status_providers, baselines


def reconcile(status: dict[str, Any], source_registry: dict[str, Any]) -> dict[str, Any]:
    status_providers, baselines = _providers(status, source_registry)
    for provider in REQUIRED_PROVIDERS:
        eligibility, reason = derive(provider, status_providers[provider], baselines[provider])
        status_providers[provider]["releaseEligibility"] = eligibility
        status_providers[provider]["releaseEligibilityReason"] = reason
    return status


def validate(status: dict[str, Any], source_registry: dict[str, Any]) -> None:
    status_providers, baselines = _providers(status, source_registry)
    for provider in REQUIRED_PROVIDERS:
        item = status_providers[provider]
        eligibility = item.get("releaseEligibility")
        reason = item.get("releaseEligibilityReason")
        if eligibility not in RELEASE_ELIGIBILITY:
            raise ReleaseEligibilityError(f"{provider} releaseEligibility must be explicit")
        expected_eligibility, expected_reason = derive(provider, item, baselines[provider])
        if eligibility != expected_eligibility or reason != expected_reason:
            raise ReleaseEligibilityError(
                f"{provider} release eligibility is stale: "
                f"stored=({eligibility!r}, {reason!r}) "
                f"expected=({expected_eligibility!r}, {expected_reason!r})"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("reconcile", "validate"))
    parser.add_argument("--status", required=True, type=Path)
    parser.add_argument("--source-registry", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        status = load_json(args.status)
        source_registry = load_json(args.source_registry)
        if args.command == "reconcile":
            reconcile(status, source_registry)
            save_json(args.status, status)
            print("provider release eligibility reconciled")
        else:
            validate(status, source_registry)
            print("provider release eligibility is valid")
        return 0
    except (ReleaseEligibilityError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
