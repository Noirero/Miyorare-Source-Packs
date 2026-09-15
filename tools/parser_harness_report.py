#!/usr/bin/env python3
"""Normalize real Kotlin parser JUnit results into Compatibility Farm evidence."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


class HarnessReportError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise HarnessReportError(f"{path} must contain a JSON object")
    return value


def parse_source_mapping(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise HarnessReportError("--source must use canonicalId=testClass")
    canonical_id, test_class = raw.split("=", 1)
    canonical_id = canonical_id.strip()
    test_class = test_class.strip()
    if not canonical_id or not test_class:
        raise HarnessReportError("--source canonicalId and testClass must be non-empty")
    return canonical_id, test_class


def _registry_ids(registry: dict[str, Any]) -> set[str]:
    sources = registry.get("sources")
    if not isinstance(sources, list) or not sources:
        raise HarnessReportError("registry.sources must be a non-empty list")
    ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("canonicalId"), str):
            raise HarnessReportError("invalid source registry entry")
        ids.add(source["canonicalId"])
    return ids


def read_junit_results(results_dir: Path) -> dict[str, dict[str, int]]:
    if not results_dir.is_dir():
        raise HarnessReportError(f"JUnit results directory does not exist: {results_dir}")
    found: dict[str, dict[str, int]] = {}
    for path in sorted(results_dir.glob("TEST-*.xml")):
        root = ET.parse(path).getroot()
        suite_name = root.attrib.get("name", "")
        tests = int(root.attrib.get("tests", "0"))
        failures = int(root.attrib.get("failures", "0"))
        errors = int(root.attrib.get("errors", "0"))
        skipped = int(root.attrib.get("skipped", "0"))
        found[suite_name] = {
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        }
    if not found:
        raise HarnessReportError(f"no TEST-*.xml files found in {results_dir}")
    return found


def build_report(
    registry: dict[str, Any],
    junit: dict[str, dict[str, int]],
    provider: str,
    mappings: list[tuple[str, str]],
) -> dict[str, Any]:
    registry_ids = _registry_ids(registry)
    if not mappings:
        raise HarnessReportError("at least one --source mapping is required")

    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []
    for canonical_id, test_class in mappings:
        if canonical_id not in registry_ids:
            raise HarnessReportError(f"parser harness source is not registered: {canonical_id}")
        if canonical_id in seen_ids:
            raise HarnessReportError(f"duplicate parser harness source: {canonical_id}")
        seen_ids.add(canonical_id)
        test = junit.get(test_class)
        if test is None:
            raise HarnessReportError(f"JUnit suite missing for {test_class}")
        if test["tests"] <= 0:
            raise HarnessReportError(f"JUnit suite executed zero tests: {test_class}")

        passed = test["failures"] == 0 and test["errors"] == 0 and test["skipped"] < test["tests"]
        results.append(
            {
                "canonicalId": canonical_id,
                "provider": provider,
                "testClass": test_class,
                "parserExecution": True,
                "tests": test["tests"],
                "failures": test["failures"],
                "errors": test["errors"],
                "skipped": test["skipped"],
                "status": "PASS" if passed else "FAIL",
            }
        )

    passing = sum(item["status"] == "PASS" for item in results)
    failing = len(results) - passing
    full = len(results) == len(registry_ids)
    suite_pass = failing == 0
    if not suite_pass:
        release_gate = "BLOCKED_REAL_PARSER_FAILURE"
    elif not full:
        release_gate = "NOT_READY_PARTIAL_PARSER_HARNESS"
    else:
        release_gate = "REAL_PARSER_READY"

    return {
        "schemaVersion": 1,
        "executionMode": "real-kotlin-parser",
        "provider": provider,
        "parserExecution": True,
        "suiteStatus": "PASS" if suite_pass else "FAIL",
        "coverage": {
            "parserExecuted": len(results),
            "totalRegistered": len(registry_ids),
            "full": full,
            "passing": passing,
            "failing": failing,
        },
        "candidatePass": bool(suite_pass and full),
        "releaseGate": release_gate,
        "publishEligible": False,
        "ownerActionRequired": False,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="compatibility/source-registry.json")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        registry = load_json(args.registry)
        junit = read_junit_results(args.results_dir)
        mappings = [parse_source_mapping(raw) for raw in args.source]
        report = build_report(registry, junit, args.provider, mappings)
        rendered = json.dumps(report, indent=2, sort_keys=True)
        print(rendered)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        return 0 if report["suiteStatus"] == "PASS" else 2
    except (HarnessReportError, OSError, json.JSONDecodeError, ET.ParseError, ValueError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
