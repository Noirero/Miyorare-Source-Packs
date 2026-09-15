#!/usr/bin/env python3
"""Provider-neutral behavioral response fixture executor.

This layer validates browse/search/details/chapters/content transformations against
stored response fixtures using a small generic extraction DSL. It deliberately does not
claim to execute the upstream Kotlin parser; reports carry parserExecution=false and can
never unlock publishing. The separate source-shape guard binds these fixtures to pinned
upstream Kotlin structure until a real parser harness is introduced.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

BEHAVIOR_CAPABILITIES = ("browse", "search", "details", "chapters", "content")
SUPPORTED_EXTRACTORS = {
    "regex-list",
    "regex-object",
    "json-list",
    "json-object",
    "json-scalar-list",
}


class BehaviorError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BehaviorError(f"{path} must contain a JSON object")
    return value


def _source_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = registry.get("sources")
    if not isinstance(sources, list) or not sources:
        raise BehaviorError("registry.sources must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("canonicalId"), str):
            raise BehaviorError("invalid registry source entry")
        result[source["canonicalId"]] = source
    return result


def _path_get(value: Any, path: str) -> Any:
    current = value
    if path == "":
        return current
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                raise BehaviorError(f"JSON path segment not found: {path}")
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index >= len(current):
                raise BehaviorError(f"JSON list index out of range: {path}")
            current = current[index]
        else:
            raise BehaviorError(f"JSON path cannot traverse segment {segment!r}: {path}")
    return current


def _regex_list(body: str, extractor: dict[str, Any]) -> list[dict[str, str]]:
    pattern = extractor.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        raise BehaviorError("regex-list extractor requires pattern")
    compiled = re.compile(pattern, re.DOTALL)
    if not compiled.groupindex:
        raise BehaviorError("regex-list pattern requires named groups")
    return [match.groupdict() for match in compiled.finditer(body)]


def _regex_object(body: str, extractor: dict[str, Any]) -> dict[str, str]:
    fields = extractor.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise BehaviorError("regex-object extractor requires fields")
    output: dict[str, str] = {}
    for name, pattern in fields.items():
        if not isinstance(name, str) or not isinstance(pattern, str) or not pattern:
            raise BehaviorError("regex-object fields must map names to regex strings")
        match = re.search(pattern, body, re.DOTALL)
        if match is None or match.lastindex is None:
            raise BehaviorError(f"regex-object field did not match with a capture: {name}")
        output[name] = match.group(1)
    return output


def _json_fields(item: Any, fields: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise BehaviorError("JSON field extraction requires an object")
    output: dict[str, Any] = {}
    for output_name, source_path in fields.items():
        if not isinstance(output_name, str) or not isinstance(source_path, str):
            raise BehaviorError("JSON fields must map string names to string paths")
        output[output_name] = _path_get(item, source_path)
    return output


def _json_extract(body: str, extractor: dict[str, Any], kind: str) -> Any:
    try:
        document = json.loads(body)
    except json.JSONDecodeError as exc:
        raise BehaviorError(f"invalid JSON response fixture: {exc}") from exc
    path = extractor.get("path", "")
    if not isinstance(path, str):
        raise BehaviorError("JSON extractor path must be a string")
    target = _path_get(document, path)

    if kind == "json-scalar-list":
        if not isinstance(target, list) or any(isinstance(item, (dict, list)) for item in target):
            raise BehaviorError("json-scalar-list path must resolve to scalar list")
        return target

    fields = extractor.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise BehaviorError(f"{kind} extractor requires fields")
    if kind == "json-object":
        return _json_fields(target, fields)
    if kind == "json-list":
        if not isinstance(target, list):
            raise BehaviorError("json-list path must resolve to list")
        return [_json_fields(item, fields) for item in target]
    raise BehaviorError(f"unsupported JSON extractor: {kind}")


def execute_case(case: dict[str, Any]) -> Any:
    response = case.get("response")
    extractor = case.get("extractor")
    if not isinstance(response, dict) or not isinstance(extractor, dict):
        raise BehaviorError("behavior case requires response and extractor objects")
    body = response.get("body")
    if not isinstance(body, str):
        raise BehaviorError("behavior response body must be a string")
    kind = extractor.get("kind")
    if kind not in SUPPORTED_EXTRACTORS:
        raise BehaviorError(f"unsupported extractor kind: {kind!r}")
    if kind == "regex-list":
        return _regex_list(body, extractor)
    if kind == "regex-object":
        return _regex_object(body, extractor)
    return _json_extract(body, extractor, kind)


def validate_suite(registry: dict[str, Any], suite: dict[str, Any]) -> list[dict[str, Any]]:
    if suite.get("schemaVersion") != 1:
        raise BehaviorError("behavior fixture schemaVersion must be 1")
    if suite.get("executionMode") != "response-fixture-contract":
        raise BehaviorError("executionMode must be response-fixture-contract")
    if suite.get("parserExecution") is not False:
        raise BehaviorError("behavioral fixture foundation must declare parserExecution=false")

    source_index = _source_index(registry)
    fixtures = suite.get("sources")
    if not isinstance(fixtures, list) or not fixtures:
        raise BehaviorError("behavior suite sources must be a non-empty list")
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []

    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise BehaviorError("behavior source entry must be an object")
        canonical_id = fixture.get("canonicalId")
        if canonical_id not in source_index:
            raise BehaviorError(f"behavior fixture source is not registered: {canonical_id!r}")
        if canonical_id in seen:
            raise BehaviorError(f"duplicate behavior fixture source: {canonical_id}")
        seen.add(canonical_id)
        source = source_index[canonical_id]

        versions = fixture.get("providerVersions")
        lkg = source.get("lastKnownGood")
        if not isinstance(versions, dict) or not isinstance(lkg, dict) or set(versions) != set(lkg):
            raise BehaviorError(f"{canonical_id}: providerVersions must match registered providers")

        cases = fixture.get("cases")
        if not isinstance(cases, dict) or set(cases) != set(BEHAVIOR_CAPABILITIES):
            raise BehaviorError(
                f"{canonical_id}: cases must contain exactly {', '.join(BEHAVIOR_CAPABILITIES)}"
            )
        for capability, case in cases.items():
            if not isinstance(case, dict) or "expected" not in case:
                raise BehaviorError(f"{canonical_id}: {capability} requires expected output")
            # Execute during validation so malformed extractors fail before reporting PASS.
            execute_case(case)
        validated.append(fixture)

    return validated


def run_suite(registry: dict[str, Any], suite: dict[str, Any]) -> dict[str, Any]:
    fixtures = validate_suite(registry, suite)
    source_index = _source_index(registry)
    results: list[dict[str, Any]] = []

    for fixture in fixtures:
        canonical_id = fixture["canonicalId"]
        source = source_index[canonical_id]
        stale = sorted(
            provider
            for provider, version in fixture["providerVersions"].items()
            if source["lastKnownGood"].get(provider) != version
        )
        failed: list[str] = []
        observed: dict[str, Any] = {}
        if not stale:
            for capability in BEHAVIOR_CAPABILITIES:
                case = fixture["cases"][capability]
                actual = execute_case(case)
                observed[capability] = actual
                if actual != case["expected"]:
                    failed.append(capability)

        if stale:
            status = "STALE_BASELINE"
            failure_class = "UPSTREAM_CHANGED"
        elif failed:
            status = "FAIL"
            failure_class = "PARSER_FAILURE"
        else:
            status = "PASS"
            failure_class = None

        results.append(
            {
                "canonicalId": canonical_id,
                "status": status,
                "staleProviders": stale,
                "failedCapabilities": failed,
                "failureClass": failure_class,
                "observed": observed,
            }
        )

    passing = sum(item["status"] == "PASS" for item in results)
    failing = sum(item["status"] == "FAIL" for item in results)
    stale_count = sum(item["status"] == "STALE_BASELINE" for item in results)
    suite_pass = failing == 0 and stale_count == 0

    return {
        "schemaVersion": 1,
        "executionMode": suite["executionMode"],
        "parserExecution": False,
        "cohort": suite.get("cohort"),
        "suiteStatus": "PASS" if suite_pass else "FAIL",
        "coverage": {
            "covered": len(results),
            "totalRegistered": len(source_index),
            "passing": passing,
            "failing": failing,
            "staleBaseline": stale_count,
        },
        "candidatePass": False,
        "releaseGate": "NOT_READY_NO_PARSER_HARNESS" if suite_pass else "BLOCKED_BEHAVIOR_FIXTURE_FAILURE",
        "publishEligible": False,
        "ownerActionRequired": False,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "run"):
        command = sub.add_parser(name)
        command.add_argument("--registry", default="compatibility/source-registry.json")
        command.add_argument("--fixtures", default="compatibility/fixtures/behavioral-seed-4.json")
        if name == "run":
            command.add_argument("--output")
    args = parser.parse_args()

    try:
        registry = load_json(args.registry)
        suite = load_json(args.fixtures)
        if args.command == "validate":
            fixtures = validate_suite(registry, suite)
            print(f"behavior fixture suite: valid ({len(fixtures)} sources)")
            return 0
        report = run_suite(registry, suite)
        rendered = json.dumps(report, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
        return 0 if report["suiteStatus"] == "PASS" else 2
    except (BehaviorError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
