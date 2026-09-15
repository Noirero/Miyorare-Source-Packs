#!/usr/bin/env python3
"""Aggregate provider-level real Kotlin parser reports into release-gate evidence.

Canonical source coverage and provider/source membership coverage are tracked separately.
A cross-provider source is not considered fully exercised merely because one provider's
implementation passed. Auto-repair evidence is accepted only when it is tied to an
observed provider/source membership and followed by a real-parser retest. The aggregate
never publishes; it only supplies trustworthy gate input for the future approve-only
state machine.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class AggregateError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AggregateError(f"{path} must contain a JSON object")
    return value


def _registry_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = registry.get("sources")
    if not isinstance(sources, list) or not sources:
        raise AggregateError("registry.sources must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise AggregateError("invalid registry source entry")
        canonical_id = source.get("canonicalId")
        providers = source.get("providers")
        if not isinstance(canonical_id, str) or not canonical_id:
            raise AggregateError("registry source canonicalId is required")
        if not isinstance(providers, list) or not providers or not all(isinstance(x, str) and x for x in providers):
            raise AggregateError(f"{canonical_id}: providers must be a non-empty string list")
        if canonical_id in result:
            raise AggregateError(f"duplicate registry source: {canonical_id}")
        result[canonical_id] = source
    return result


def _repair_index(
    repairs: list[dict[str, Any]],
    source_index: dict[str, dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for repair in repairs:
        if not isinstance(repair, dict):
            raise AggregateError("invalid repair report")
        canonical_id = repair.get("canonicalId")
        provider = repair.get("provider")
        if canonical_id not in source_index:
            raise AggregateError(f"repair references unregistered source {canonical_id!r}")
        if not isinstance(provider, str) or provider not in source_index[canonical_id]["providers"]:
            raise AggregateError(f"repair {canonical_id}: provider {provider!r} is not a registered membership")
        if repair.get("status") not in {"APPLIED", "ALREADY_APPLIED"}:
            raise AggregateError(f"repair {canonical_id}@{provider}: unsupported repair status")
        if repair.get("requiresRetest") is not True:
            raise AggregateError(f"repair {canonical_id}@{provider}: requiresRetest must be true")
        if repair.get("ownerActionRequired") is not False:
            raise AggregateError(f"repair {canonical_id}@{provider}: ownerActionRequired must remain false")
        if repair.get("publishEligible") is not False:
            raise AggregateError(f"repair {canonical_id}@{provider}: repair evidence cannot be publish eligible")
        recipe_id = repair.get("recipeId")
        if not isinstance(recipe_id, str) or not recipe_id:
            raise AggregateError(f"repair {canonical_id}@{provider}: recipeId is required")
        changes = repair.get("changes")
        if not isinstance(changes, int) or changes < 0:
            raise AggregateError(f"repair {canonical_id}@{provider}: changes must be a non-negative integer")
        if repair["status"] == "APPLIED" and changes <= 0:
            raise AggregateError(f"repair {canonical_id}@{provider}: APPLIED repair must change source")
        membership = (canonical_id, provider)
        if membership in result:
            raise AggregateError(f"duplicate repair evidence for {canonical_id}@{provider}")
        result[membership] = repair
    return result


def aggregate_reports(
    registry: dict[str, Any],
    reports: list[dict[str, Any]],
    repairs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_index = _registry_index(registry)
    if not reports:
        raise AggregateError("at least one real parser report is required")
    repair_index = _repair_index(repairs or [], source_index)

    required_memberships = {
        (canonical_id, provider)
        for canonical_id, source in source_index.items()
        for provider in source["providers"]
    }
    observed_memberships: set[tuple[str, str]] = set()
    canonical: dict[str, dict[str, Any]] = {}
    providers_seen: set[str] = set()
    duplicate_memberships: set[tuple[str, str]] = set()
    repair_retest_pass = 0
    repair_retest_fail = 0

    for report in reports:
        if report.get("executionMode") != "real-kotlin-parser" or report.get("parserExecution") is not True:
            raise AggregateError("all inputs must be real-kotlin-parser reports with parserExecution=true")
        provider = report.get("provider")
        if not isinstance(provider, str) or not provider:
            raise AggregateError("provider-level parser report is missing provider")
        providers_seen.add(provider)
        results = report.get("results")
        if not isinstance(results, list) or not results:
            raise AggregateError(f"provider {provider}: parser report results must be non-empty")

        for result in results:
            if not isinstance(result, dict):
                raise AggregateError(f"provider {provider}: invalid parser result")
            canonical_id = result.get("canonicalId")
            if canonical_id not in source_index:
                raise AggregateError(f"provider {provider}: unregistered source {canonical_id!r}")
            if provider not in source_index[canonical_id]["providers"]:
                raise AggregateError(f"{canonical_id}: provider {provider} is not registered for this source")
            if result.get("provider") != provider:
                raise AggregateError(f"{canonical_id}: result provider does not match report provider")
            if result.get("parserExecution") is not True:
                raise AggregateError(f"{canonical_id}: result is missing parserExecution=true")
            if result.get("status") not in {"PASS", "FAIL"}:
                raise AggregateError(f"{canonical_id}: parser result status must be PASS or FAIL")

            membership = (canonical_id, provider)
            if membership in observed_memberships:
                duplicate_memberships.add(membership)
                continue
            observed_memberships.add(membership)

            repair = repair_index.get(membership)
            repair_evidence = None
            maintenance_outcome = "UNCHANGED"
            if repair is not None:
                retest_passed = result["status"] == "PASS"
                if retest_passed:
                    repair_retest_pass += 1
                    maintenance_outcome = "AUTO_REPAIRED"
                else:
                    repair_retest_fail += 1
                    maintenance_outcome = "AUTO_REPAIR_RETEST_FAILED"
                repair_evidence = {
                    "recipeId": repair["recipeId"],
                    "status": repair["status"],
                    "changes": repair["changes"],
                    "alreadyAppliedCalls": repair.get("alreadyAppliedCalls", 0),
                    "beforeSha256": repair.get("beforeSha256"),
                    "afterSha256": repair.get("afterSha256"),
                    "retestValidated": retest_passed,
                }

            item = canonical.setdefault(
                canonical_id,
                {
                    "canonicalId": canonical_id,
                    "requiredProviders": sorted(source_index[canonical_id]["providers"]),
                    "providerExecutions": [],
                },
            )
            execution = {
                "provider": provider,
                "status": result["status"],
                "testClass": result.get("testClass"),
                "tests": result.get("tests", 0),
                "failures": result.get("failures", 0),
                "errors": result.get("errors", 0),
                "skipped": result.get("skipped", 0),
                "maintenanceOutcome": maintenance_outcome,
            }
            if repair_evidence is not None:
                execution["repairEvidence"] = repair_evidence
            item["providerExecutions"].append(execution)

    if duplicate_memberships:
        rendered = ", ".join(f"{source}@{provider}" for source, provider in sorted(duplicate_memberships))
        raise AggregateError(f"duplicate parser execution membership(s): {rendered}")

    unretested_repairs = sorted(set(repair_index) - observed_memberships)
    if unretested_repairs:
        rendered = ", ".join(f"{source}@{provider}" for source, provider in unretested_repairs)
        raise AggregateError(f"repair evidence without real-parser retest: {rendered}")

    results_out: list[dict[str, Any]] = []
    failing_memberships = 0
    fully_exercised_sources = 0
    for canonical_id, item in sorted(canonical.items()):
        item["providerExecutions"].sort(key=lambda x: x["provider"])
        executed_providers = {entry["provider"] for entry in item["providerExecutions"]}
        required_providers = set(item["requiredProviders"])
        missing = sorted(required_providers - executed_providers)
        failed = sorted(entry["provider"] for entry in item["providerExecutions"] if entry["status"] != "PASS")
        repaired = sorted(
            entry["provider"]
            for entry in item["providerExecutions"]
            if entry.get("maintenanceOutcome") == "AUTO_REPAIRED"
        )
        failing_memberships += len(failed)
        fully_exercised = not missing and not failed
        if fully_exercised:
            fully_exercised_sources += 1
        item.update(
            {
                "missingProviders": missing,
                "failedProviders": failed,
                "autoRepairedProviders": repaired,
                "fullyExercised": fully_exercised,
                "status": "FAIL" if failed else ("PARTIAL" if missing else "PASS"),
                "maintenanceOutcome": "FAILED" if failed else ("AUTO_REPAIRED" if repaired else "UNCHANGED"),
            }
        )
        results_out.append(item)

    total_sources = len(source_index)
    canonical_executed = len(canonical)
    total_memberships = len(required_memberships)
    membership_executed = len(observed_memberships)
    membership_missing = total_memberships - membership_executed
    all_memberships_pass = failing_memberships == 0
    full_membership_coverage = membership_executed == total_memberships
    full_canonical_coverage = canonical_executed == total_sources

    if failing_memberships:
        release_gate = "BLOCKED_REAL_PARSER_FAILURE"
        suite_status = "FAIL"
    elif not full_membership_coverage or not full_canonical_coverage:
        release_gate = "NOT_READY_PARTIAL_PARSER_HARNESS"
        suite_status = "PASS"
    else:
        release_gate = "REAL_PARSER_READY"
        suite_status = "PASS"

    return {
        "schemaVersion": 1,
        "executionMode": "real-kotlin-parser-aggregate",
        "parserExecution": True,
        "providers": sorted(providers_seen),
        "suiteStatus": suite_status,
        "coverage": {
            "canonicalExecuted": canonical_executed,
            "totalRegisteredSources": total_sources,
            "fullyExercisedSources": fully_exercised_sources,
            "providerMembershipsExecuted": membership_executed,
            "totalProviderMemberships": total_memberships,
            "missingProviderMemberships": membership_missing,
            "failingProviderMemberships": failing_memberships,
            "fullCanonicalCoverage": full_canonical_coverage,
            "fullProviderMembershipCoverage": full_membership_coverage,
        },
        "repairEvidence": {
            "reportedMemberships": len(repair_index),
            "validatedByRealParserRetest": repair_retest_pass,
            "failedRealParserRetest": repair_retest_fail,
        },
        "candidatePass": bool(all_memberships_pass and full_membership_coverage and full_canonical_coverage),
        "releaseGate": release_gate,
        "publishEligible": False,
        "ownerActionRequired": False,
        "results": results_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="compatibility/source-registry.json")
    parser.add_argument("--report", action="append", required=True)
    parser.add_argument("--repair-report", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        registry = load_json(args.registry)
        reports = [load_json(path) for path in args.report]
        repairs = [load_json(path) for path in args.repair_report]
        aggregate = aggregate_reports(registry, reports, repairs)
        rendered = json.dumps(aggregate, indent=2, sort_keys=True)
        print(rendered)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        return 0 if aggregate["suiteStatus"] == "PASS" else 2
    except (AggregateError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
