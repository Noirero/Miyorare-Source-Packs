#!/usr/bin/env python3
"""Deterministic Compatibility Farm foundation.

This runner consumes normalized adapter fixtures, validates them against the source
registry and compatibility contract, and emits provider-neutral evidence. It is
intentionally unable to make a full candidate PASS while fixture coverage is partial.

The fixtures are bound to each source's last-known-good provider SHAs. When an upstream
pin advances, old fixtures become STALE_BASELINE instead of silently passing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class FarmError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FarmError(f"{path} must contain a JSON object")
    return value


def _string_set(value: Any, label: str) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise FarmError(f"{label} must be a non-empty-string list")
    if len(value) != len(set(value)):
        raise FarmError(f"{label} contains duplicates")
    return set(value)


def _source_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = registry.get("sources")
    if not isinstance(sources, list) or not sources:
        raise FarmError("registry.sources must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise FarmError("registry source entry must be an object")
        canonical_id = source.get("canonicalId")
        if not isinstance(canonical_id, str) or not canonical_id:
            raise FarmError("registry source canonicalId is required")
        if canonical_id in result:
            raise FarmError(f"duplicate registry source: {canonical_id}")
        result[canonical_id] = source
    return result


def _validate_auth(source: dict[str, Any], fixture: dict[str, Any]) -> None:
    auth_type = source["authType"]
    auth = fixture["capabilities"]["authenticate"]
    if auth.get("status") != "PASS":
        return
    evidence = auth.get("evidence")
    if not isinstance(evidence, dict):
        raise FarmError(f"{source['canonicalId']}: authenticate.evidence must be an object")
    if evidence.get("mode") != auth_type:
        raise FarmError(f"{source['canonicalId']}: auth fixture mode must match registry authType")

    if auth_type == "NO_AUTH":
        return

    if evidence.get("credentialed") != "PASS":
        raise FarmError(f"{source['canonicalId']}: authenticated fixture must demonstrate credentialed PASS")
    if evidence.get("anonymous") not in {"AUTH_REQUIRED", "PASS"}:
        raise FarmError(
            f"{source['canonicalId']}: auth-aware fixture must classify anonymous access as AUTH_REQUIRED or PASS"
        )


def _validate_content(source: dict[str, Any], fixture: dict[str, Any], contract: dict[str, Any]) -> None:
    profile = source["contentProfile"]
    profiles = contract.get("contentProfiles")
    if not isinstance(profiles, dict) or profile not in profiles:
        raise FarmError(f"{source['canonicalId']}: unknown content profile {profile!r}")
    required_steps = _string_set(profiles[profile], f"contract.contentProfiles.{profile}")
    content = fixture["capabilities"]["content"]
    if content.get("status") != "PASS":
        return
    evidence = content.get("evidence")
    if not isinstance(evidence, dict):
        raise FarmError(f"{source['canonicalId']}: content.evidence must be an object")
    missing = sorted(step for step in required_steps if evidence.get(step) is not True)
    if missing:
        raise FarmError(
            f"{source['canonicalId']}: PASS content evidence is missing required successful step(s): {', '.join(missing)}"
        )


def validate_suite(
    contract: dict[str, Any], registry: dict[str, Any], suite: dict[str, Any]
) -> list[dict[str, Any]]:
    if suite.get("schemaVersion") != 1:
        raise FarmError("fixture schemaVersion must be 1")
    if suite.get("executionMode") != "normalized-adapter-fixture":
        raise FarmError("executionMode must be normalized-adapter-fixture")

    required_capabilities = _string_set(contract.get("capabilities"), "contract.capabilities")
    registry_sources = _source_index(registry)
    fixtures = suite.get("sources")
    if not isinstance(fixtures, list) or not fixtures:
        raise FarmError("fixture sources must be a non-empty list")

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise FarmError("fixture source entry must be an object")
        canonical_id = fixture.get("canonicalId")
        if canonical_id not in registry_sources:
            raise FarmError(f"fixture source is not registered: {canonical_id!r}")
        if canonical_id in seen:
            raise FarmError(f"duplicate fixture source: {canonical_id}")
        seen.add(canonical_id)
        source = registry_sources[canonical_id]

        for field in ("adapterFamily", "contentProfile", "authType"):
            if fixture.get(field) != source.get(field):
                raise FarmError(f"{canonical_id}: fixture {field} does not match source registry")

        fixture_providers = fixture.get("providerVersions")
        source_lkg = source.get("lastKnownGood")
        if not isinstance(fixture_providers, dict) or not isinstance(source_lkg, dict):
            raise FarmError(f"{canonical_id}: provider version maps are required")
        if set(fixture_providers) != set(source_lkg):
            raise FarmError(f"{canonical_id}: providerVersions must cover exactly the registered providers")
        for provider, version in fixture_providers.items():
            if not isinstance(version, str) or not version:
                raise FarmError(f"{canonical_id}: invalid provider version for {provider}")

        fixture_overlays = _string_set(fixture.get("protectedOverlays", []), f"{canonical_id}.protectedOverlays")
        registry_overlays = _string_set(source.get("protectedOverlays", []), f"{canonical_id}.registryProtectedOverlays")
        if fixture_overlays != registry_overlays:
            raise FarmError(f"{canonical_id}: protected overlay fixture does not match registry")

        capabilities = fixture.get("capabilities")
        if not isinstance(capabilities, dict) or set(capabilities) != required_capabilities:
            raise FarmError(f"{canonical_id}: fixture must contain exactly the compatibility contract capabilities")
        for capability, observation in capabilities.items():
            if not isinstance(observation, dict):
                raise FarmError(f"{canonical_id}: capability {capability} must be an object")
            if observation.get("status") not in {"PASS", "FAIL"}:
                raise FarmError(f"{canonical_id}: capability {capability} status must be PASS or FAIL")
            if not isinstance(observation.get("evidence"), dict):
                raise FarmError(f"{canonical_id}: capability {capability} evidence must be an object")

        _validate_auth(source, fixture)
        _validate_content(source, fixture, contract)
        validated.append(fixture)

    return validated


def run_suite(contract: dict[str, Any], registry: dict[str, Any], suite: dict[str, Any]) -> dict[str, Any]:
    fixtures = validate_suite(contract, registry, suite)
    registry_sources = _source_index(registry)
    results: list[dict[str, Any]] = []

    for fixture in fixtures:
        canonical_id = fixture["canonicalId"]
        source = registry_sources[canonical_id]
        stale_providers = sorted(
            provider
            for provider, fixture_version in fixture["providerVersions"].items()
            if source["lastKnownGood"].get(provider) != fixture_version
        )
        failed_capabilities = sorted(
            capability
            for capability, observation in fixture["capabilities"].items()
            if observation["status"] != "PASS"
        )

        if stale_providers:
            status = "STALE_BASELINE"
            failure_class = "UPSTREAM_CHANGED"
        elif failed_capabilities:
            status = "FAIL"
            failure_class = "PARSER_FAILURE"
        else:
            status = "PASS"
            failure_class = None

        results.append(
            {
                "canonicalId": canonical_id,
                "status": status,
                "authType": source["authType"],
                "contentProfile": source["contentProfile"],
                "failedCapabilities": failed_capabilities,
                "staleProviders": stale_providers,
                "failureClass": failure_class,
            }
        )

    passing = sum(item["status"] == "PASS" for item in results)
    failing = sum(item["status"] == "FAIL" for item in results)
    stale = sum(item["status"] == "STALE_BASELINE" for item in results)
    covered = len(results)
    total = len(registry_sources)
    full_coverage = covered == total
    suite_pass = failing == 0 and stale == 0

    if not suite_pass:
        release_gate = "BLOCKED_DETERMINISTIC_FAILURE"
    elif not full_coverage:
        release_gate = "NOT_READY_PARTIAL_COVERAGE"
    else:
        release_gate = "DETERMINISTIC_READY"

    return {
        "schemaVersion": 1,
        "executionMode": suite["executionMode"],
        "cohort": suite.get("cohort"),
        "suiteStatus": "PASS" if suite_pass else "FAIL",
        "coverage": {
            "covered": covered,
            "totalRegistered": total,
            "full": full_coverage,
            "passing": passing,
            "failing": failing,
            "staleBaseline": stale,
        },
        "candidatePass": bool(suite_pass and full_coverage),
        "releaseGate": release_gate,
        "publishEligible": False,
        "ownerActionRequired": False,
        "results": results,
    }


def _paths(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return load_json(args.contract), load_json(args.registry), load_json(args.fixtures)


def _cmd_validate(args: argparse.Namespace) -> int:
    contract, registry, suite = _paths(args)
    fixtures = validate_suite(contract, registry, suite)
    print(f"deterministic fixture suite: valid ({len(fixtures)} sources)")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    contract, registry, suite = _paths(args)
    report = run_suite(contract, registry, suite)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["suiteStatus"] == "PASS" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "run"):
        command = sub.add_parser(name)
        command.add_argument("--contract", default="compatibility/contract.json")
        command.add_argument("--registry", default="compatibility/source-registry.json")
        command.add_argument("--fixtures", default="compatibility/fixtures/deterministic-seed-3.json")
        if name == "run":
            command.add_argument("--output")
            command.set_defaults(func=_cmd_run)
        else:
            command.set_defaults(func=_cmd_validate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except (FarmError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
