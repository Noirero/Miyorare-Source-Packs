#!/usr/bin/env python3
"""Aggregate provider-level real Kotlin parser reports into release-gate evidence.

Canonical source coverage and provider/source membership coverage are tracked separately.
A cross-provider source is not considered fully exercised merely because one provider's
implementation passed. The aggregate never publishes; it only supplies trustworthy gate
input for the future approve-only state machine.
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


def aggregate_reports(registry: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, Any]:
    source_index = _registry_index(registry)
    if not reports:
        raise AggregateError("at least one real parser report is required")

    required_memberships = {
        (canonical_id, provider)
        for canonical_id, source in source_index.items()
        for provider in source["providers"]
    }
    observed_memberships: set[tuple[str, str]] = set()
    canonical: dict[str, dict[str, Any]] = {}
    providers_seen: set[str] = set()
    duplicate_memberships: set[tuple[str, str]] = set()

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

            item = canonical.setdefault(
                canonical_id,
                {
                    "canonicalId": canonical_id,
                    "requiredProviders": sorted(source_index[canonical_id]["providers"]),
                    "providerExecutions": [],
                },
            )
            item["providerExecutions"].append(
                {
                    "provider": provider,
                    "status": result["status"],
                    "testClass": result.get("testClass"),
                    "tests": result.get("tests", 0),
                    "failures": result.get("failures", 0),
                    "errors": result.get("errors", 0),
                    "skipped": result.get("skipped", 0),
                }
            )

    if duplicate_memberships:
        rendered = ", ".join(f"{source}@{provider}" for source, provider in sorted(duplicate_memberships))
        raise AggregateError(f"duplicate parser execution membership(s): {rendered}")

    results_out: list[dict[str, Any]] = []
    failing_memberships = 0
    fully_exercised_sources = 0
    for canonical_id, item in sorted(canonical.items()):
        item["providerExecutions"].sort(key=lambda x: x["provider"])
        executed_providers = {entry["provider"] for entry in item["providerExecutions"]}
        required_providers = set(item["requiredProviders"])
        missing = sorted(required_providers - executed_providers)
        failed = sorted(entry["provider"] for entry in item["providerExecutions"] if entry["status"] != "PASS")
        failing_memberships += len(failed)
        fully_exercised = not missing and not failed
        if fully_exercised:
            fully_exercised_sources += 1
        item.update(
            {
                "missingProviders": missing,
                "failedProviders": failed,
                "fullyExercised": fully_exercised,
                "status": "FAIL" if failed else ("PARTIAL" if missing else "PASS"),
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        registry = load_json(args.registry)
        reports = [load_json(path) for path in args.report]
        aggregate = aggregate_reports(registry, reports)
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
