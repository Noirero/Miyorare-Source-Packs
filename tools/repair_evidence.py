#!/usr/bin/env python3
"""Attach validated auto-repair outcomes to real-parser aggregate evidence.

This layer intentionally sits after raw parser aggregation. A repair is credited only
when the exact canonical-source/provider membership was actually executed again by the
real Kotlin parser harness. Repair evidence can never make a partial farm publishable.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


class RepairEvidenceError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RepairEvidenceError(f"{path} must contain a JSON object")
    return value


def enrich_aggregate(aggregate: dict[str, Any], repair_reports: list[dict[str, Any]]) -> dict[str, Any]:
    if aggregate.get("executionMode") != "real-kotlin-parser-aggregate" or aggregate.get("parserExecution") is not True:
        raise RepairEvidenceError("aggregate must be real-kotlin-parser-aggregate evidence")

    output = copy.deepcopy(aggregate)
    results = output.get("results")
    if not isinstance(results, list):
        raise RepairEvidenceError("aggregate.results must be a list")

    sources: dict[str, dict[str, Any]] = {}
    executions: dict[tuple[str, str], dict[str, Any]] = {}
    for source in results:
        if not isinstance(source, dict) or not isinstance(source.get("canonicalId"), str):
            raise RepairEvidenceError("invalid aggregate source result")
        canonical_id = source["canonicalId"]
        if canonical_id in sources:
            raise RepairEvidenceError(f"duplicate aggregate source result: {canonical_id}")
        sources[canonical_id] = source

        provider_executions = source.get("providerExecutions")
        if not isinstance(provider_executions, list):
            raise RepairEvidenceError(f"{canonical_id}: providerExecutions must be a list")
        for execution in provider_executions:
            if not isinstance(execution, dict) or not isinstance(execution.get("provider"), str):
                raise RepairEvidenceError(f"{canonical_id}: invalid provider execution")
            membership = (canonical_id, execution["provider"])
            if membership in executions:
                raise RepairEvidenceError(
                    f"duplicate aggregate parser execution: {canonical_id}@{execution['provider']}"
                )
            executions[membership] = execution

    seen: set[tuple[str, str]] = set()
    successful = 0
    failed_retests = 0
    applied_changes = 0
    validated_memberships: list[dict[str, Any]] = []

    for repair in repair_reports:
        canonical_id = repair.get("canonicalId")
        provider = repair.get("provider")
        recipe_id = repair.get("recipeId")
        status = repair.get("status")
        changes = repair.get("changes")
        if not all(isinstance(x, str) and x for x in (canonical_id, provider, recipe_id)):
            raise RepairEvidenceError("repair report requires canonicalId, provider and recipeId")
        if status not in {"APPLIED", "ALREADY_APPLIED"}:
            raise RepairEvidenceError(f"{canonical_id}@{provider}: invalid repair status {status!r}")
        if not isinstance(changes, int) or changes < 0:
            raise RepairEvidenceError(f"{canonical_id}@{provider}: changes must be a non-negative integer")
        if status == "APPLIED" and changes <= 0:
            raise RepairEvidenceError(f"{canonical_id}@{provider}: APPLIED repair must contain a source change")
        if status == "ALREADY_APPLIED" and changes != 0:
            raise RepairEvidenceError(f"{canonical_id}@{provider}: ALREADY_APPLIED repair must have zero changes")
        if repair.get("requiresRetest") is not True:
            raise RepairEvidenceError(f"{canonical_id}@{provider}: repair must require retest")
        if repair.get("ownerActionRequired") is not False or repair.get("publishEligible") is not False:
            raise RepairEvidenceError(f"{canonical_id}@{provider}: repair evidence violates approve-only safety")

        membership = (canonical_id, provider)
        if membership in seen:
            raise RepairEvidenceError(f"duplicate repair evidence for {canonical_id}@{provider}")
        seen.add(membership)
        execution = executions.get(membership)
        source = sources.get(canonical_id)
        if execution is None or source is None:
            raise RepairEvidenceError(f"repair evidence has no matching parser execution: {canonical_id}@{provider}")

        retest_passed = execution.get("status") == "PASS"
        maintenance_outcome = "AUTO_REPAIRED" if retest_passed else "AUTO_REPAIR_RETEST_FAILED"
        execution["maintenanceOutcome"] = maintenance_outcome
        execution["repairEvidence"] = {
            "autoRepair": True,
            "recipeId": recipe_id,
            "status": status,
            "changes": changes,
            "alreadyAppliedCalls": repair.get("alreadyAppliedCalls", 0),
            "beforeSha256": repair.get("beforeSha256"),
            "afterSha256": repair.get("afterSha256"),
            "retestPassed": retest_passed,
            "ownerActionRequired": False,
            "publishEligible": False,
        }

        repaired_providers = source.setdefault("autoRepairedProviders", [])
        if not isinstance(repaired_providers, list):
            raise RepairEvidenceError(f"{canonical_id}: autoRepairedProviders must be a list")
        if provider not in repaired_providers:
            repaired_providers.append(provider)
            repaired_providers.sort()
        source["maintenanceOutcome"] = maintenance_outcome

        applied_changes += changes
        if retest_passed:
            successful += 1
        else:
            failed_retests += 1
        validated_memberships.append(
            {
                "canonicalId": canonical_id,
                "provider": provider,
                "recipeId": recipe_id,
                "repairStatus": status,
                "retestPassed": retest_passed,
                "maintenanceOutcome": maintenance_outcome,
            }
        )

    coverage = output.setdefault("coverage", {})
    if not isinstance(coverage, dict):
        raise RepairEvidenceError("aggregate.coverage must be an object")
    coverage.update(
        {
            "autoRepairAttempts": len(repair_reports),
            "successfulAutoRepairs": successful,
            "failedAutoRepairRetests": failed_retests,
            "autoRepairChanges": applied_changes,
        }
    )

    output["executionMode"] = "real-kotlin-parser-aggregate-with-repair-evidence"
    output["repairEvidencePresent"] = bool(repair_reports)
    output["repairEvidence"] = {
        "reportedMemberships": len(repair_reports),
        "validatedByRealParserRetest": successful,
        "failedRealParserRetest": failed_retests,
        "validatedMemberships": validated_memberships,
    }
    output["ownerActionRequired"] = False
    output["publishEligible"] = False
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--repair-report", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        aggregate = load_json(args.aggregate)
        repairs = [load_json(path) for path in args.repair_report]
        evidence = enrich_aggregate(aggregate, repairs)
        rendered = json.dumps(evidence, indent=2, sort_keys=True)
        print(rendered)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        return 0 if evidence.get("suiteStatus") == "PASS" else 2
    except (RepairEvidenceError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
