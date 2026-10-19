#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROVIDER = "gekkoushi"
LANGUAGES = ("en", "id")
VALID_STATUSES = {"PASS", "FAIL"}


class CanaryError(ValueError):
    pass


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CanaryError(f"{path}: expected JSON object")
    return value


def save(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise CanaryError(f"{label} must be a lowercase 40-character commit SHA")
    return value


def provider_binding(status: dict[str, Any]) -> tuple[str, str]:
    providers = status.get("providers")
    automation = status.get("automation")
    if not isinstance(providers, dict) or not isinstance(automation, dict):
        raise CanaryError("status providers/automation are required")
    provider = providers.get(PROVIDER)
    candidates = automation.get("candidates")
    candidate = candidates.get(PROVIDER) if isinstance(candidates, dict) else None
    if not isinstance(provider, dict) or not isinstance(candidate, dict):
        raise CanaryError("Gekkoushi provider and candidate bindings are required")

    active = require_sha(provider.get("activeCommit"), "gekkoushi.activeCommit")
    lkg = require_sha(provider.get("lastKnownGood"), "gekkoushi.lastKnownGood")
    current = require_sha(candidate.get("current"), "gekkoushi.candidate.current")
    candidate_sha = require_sha(candidate.get("candidate"), "gekkoushi.candidate.candidate")
    if active != lkg:
        raise CanaryError("Gekkoushi active commit must equal lastKnownGood before A6")
    if current != lkg:
        raise CanaryError("Gekkoushi candidate baseline must equal lastKnownGood before A6")
    if candidate_sha == lkg:
        raise CanaryError("A6 requires a distinct Gekkoushi candidate")
    return lkg, candidate_sha


def registry_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = registry.get("sources")
    if not isinstance(rows, list):
        raise CanaryError("registry.sources must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        canonical_id = row.get("canonicalId")
        if isinstance(canonical_id, str) and canonical_id:
            result[canonical_id] = row
    return result


def select_canary_memberships(
    registry: dict[str, Any],
    parser_plan: dict[str, Any],
    status: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    if limit < 2:
        raise CanaryError("canary limit must be at least 2")
    if parser_plan.get("provider") != PROVIDER:
        raise CanaryError("parser plan must be Gekkoushi-only")
    include = parser_plan.get("include")
    if not isinstance(include, list) or len(include) < 2:
        raise CanaryError("Gekkoushi parser plan must contain at least two ACTIVE memberships")

    lkg, candidate_sha = provider_binding(status)
    sources = registry_index(registry)
    eligible: list[dict[str, Any]] = []
    for raw in include:
        if not isinstance(raw, dict) or raw.get("provider") != PROVIDER:
            continue
        recipes = raw.get("repairRecipes", [])
        if recipes not in (None, []):
            continue
        canonical_id = raw.get("canonicalId")
        source = sources.get(canonical_id) if isinstance(canonical_id, str) else None
        if not isinstance(source, dict):
            raise CanaryError(f"parser-plan membership missing from registry: {canonical_id!r}")
        language = source.get("language")
        if language not in LANGUAGES:
            continue
        test_class = raw.get("testClass")
        family_id = raw.get("familyId")
        if not isinstance(test_class, str) or not test_class or not isinstance(family_id, str) or not family_id:
            raise CanaryError(f"invalid Gekkoushi parser-plan row for {canonical_id}")
        row = dict(raw)
        row["language"] = language
        eligible.append(row)

    eligible.sort(key=lambda row: (str(row["language"]), str(row["canonicalId"]), str(row["familyId"])))
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for language in LANGUAGES:
        row = next((item for item in eligible if item["language"] == language), None)
        if row is None:
            raise CanaryError(f"A6 requires at least one non-repair ACTIVE Gekkoushi {language} membership")
        selected.append(row)
        selected_ids.add(str(row["canonicalId"]))

    for row in eligible:
        if len(selected) >= limit:
            break
        canonical_id = str(row["canonicalId"])
        if canonical_id in selected_ids:
            continue
        selected.append(row)
        selected_ids.add(canonical_id)

    if len(selected) < 2:
        raise CanaryError("A6 could not select enough isolated Gekkoushi memberships")
    return {
        "schemaVersion": 1,
        "phase": "A6_GEKKOUSHI_CANARY",
        "provider": PROVIDER,
        "lastKnownGood": lkg,
        "candidate": candidate_sha,
        "selectionPolicy": {
            "maxMemberships": limit,
            "languagesRequired": list(LANGUAGES),
            "repairRecipesAllowed": False,
            "activeMembershipsOnly": True,
        },
        "membershipCount": len(selected),
        "include": selected,
    }


def _aggregate_executions(aggregate: dict[str, Any]) -> dict[str, str]:
    executions: dict[str, str] = {}
    results = aggregate.get("results")
    if not isinstance(results, list):
        raise CanaryError("aggregate.results must be a list")
    for source in results:
        if not isinstance(source, dict):
            continue
        canonical_id = source.get("canonicalId")
        provider_executions = source.get("providerExecutions")
        if not isinstance(canonical_id, str) or not isinstance(provider_executions, list):
            continue
        for execution in provider_executions:
            if not isinstance(execution, dict) or execution.get("provider") != PROVIDER:
                continue
            status = execution.get("status")
            if status not in VALID_STATUSES:
                raise CanaryError(f"invalid Gekkoushi aggregate status for {canonical_id}: {status!r}")
            if canonical_id in executions:
                raise CanaryError(f"duplicate Gekkoushi aggregate execution: {canonical_id}")
            executions[canonical_id] = str(status)
    return executions


def build_verdict(
    plan: dict[str, Any],
    aggregate: dict[str, Any],
    remote_status: dict[str, Any],
    foundation_sha: str,
) -> tuple[dict[str, Any], bool]:
    exact_foundation = require_sha(foundation_sha, "foundation SHA")
    if plan.get("phase") != "A6_GEKKOUSHI_CANARY" or plan.get("provider") != PROVIDER:
        raise CanaryError("invalid A6 canary plan")
    planned = plan.get("include")
    if not isinstance(planned, list) or not planned:
        raise CanaryError("A6 canary plan has no memberships")
    planned_ids = [row.get("canonicalId") for row in planned if isinstance(row, dict)]
    if any(not isinstance(value, str) or not value for value in planned_ids) or len(set(planned_ids)) != len(planned_ids):
        raise CanaryError("A6 planned canonical IDs must be unique non-empty strings")

    executions = _aggregate_executions(aggregate)
    missing = sorted(set(planned_ids) - set(executions))
    unexpected = sorted(set(executions) - set(planned_ids))
    passed = sorted(canonical_id for canonical_id in planned_ids if executions.get(canonical_id) == "PASS")
    failed = sorted(canonical_id for canonical_id in planned_ids if executions.get(canonical_id) == "FAIL")

    remote_lkg, _ = provider_binding(remote_status)
    expected_lkg = require_sha(plan.get("lastKnownGood"), "plan.lastKnownGood")
    lkg_unchanged = remote_lkg == expected_lkg
    all_executed = not missing and not unexpected and len(executions) == len(planned_ids)
    accepted = all_executed and bool(passed) and lkg_unchanged

    verdict = {
        "schemaVersion": 1,
        "phase": "A6_GEKKOUSHI_CANARY",
        "provider": PROVIDER,
        "foundationSha": exact_foundation,
        "candidate": require_sha(plan.get("candidate"), "plan.candidate"),
        "lastKnownGood": expected_lkg,
        "membershipCount": len(planned_ids),
        "passingMemberships": passed,
        "failingMemberships": failed,
        "missingMemberships": missing,
        "unexpectedMemberships": unexpected,
        "allCanaryMembershipsExecuted": all_executed,
        "atLeastOneCanaryPassed": bool(passed),
        "canaryAllPassed": all_executed and not failed,
        "parserFailuresCancelUnrelatedSources": False,
        "isolatedFailureEvidencePreserved": all_executed,
        "remoteLastKnownGood": remote_lkg,
        "lastKnownGoodUnchanged": lkg_unchanged,
        "foundationMutationAttempted": False,
        "promotionAttempted": False,
        "accepted": accepted,
    }
    return verdict, accepted


def main() -> int:
    parser = argparse.ArgumentParser(description="Source Lab A6 read-only Gekkoushi canary helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--registry", required=True)
    plan.add_argument("--parser-plan", required=True)
    plan.add_argument("--status", required=True)
    plan.add_argument("--limit", type=int, default=4)
    plan.add_argument("--output", required=True)

    verdict = sub.add_parser("verdict")
    verdict.add_argument("--plan", required=True)
    verdict.add_argument("--aggregate", required=True)
    verdict.add_argument("--remote-status", required=True)
    verdict.add_argument("--foundation-sha", required=True)
    verdict.add_argument("--output", required=True)

    args = parser.parse_args()
    if args.command == "plan":
        result = select_canary_memberships(
            load(args.registry), load(args.parser_plan), load(args.status), max(2, args.limit)
        )
        save(args.output, result)
        print(json.dumps({
            "candidate": result["candidate"],
            "lastKnownGood": result["lastKnownGood"],
            "membershipCount": result["membershipCount"],
        }, sort_keys=True))
        return 0

    result, accepted = build_verdict(
        load(args.plan), load(args.aggregate), load(args.remote_status), args.foundation_sha
    )
    save(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
