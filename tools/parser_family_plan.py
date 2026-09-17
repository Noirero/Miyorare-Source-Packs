#!/usr/bin/env python3
"""Validate and expand declarative real-parser family execution plans.

The planner intentionally contains no source-name special cases. Source/provider membership
comes from source-registry.json; parser-families.json only describes how an implementation
family is exercised. CI can consume the resulting matrix instead of hardcoding each source
in workflow YAML.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class ParserFamilyPlanError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _registry_sources(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = registry.get("sources")
    if not isinstance(sources, list):
        raise ParserFamilyPlanError("registry.sources must be a list")
    indexed: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ParserFamilyPlanError("registry source entries must be objects")
        canonical_id = source.get("canonicalId")
        if not isinstance(canonical_id, str) or not canonical_id:
            raise ParserFamilyPlanError("registry source canonicalId must be a non-empty string")
        if canonical_id in indexed:
            raise ParserFamilyPlanError(f"duplicate registry canonicalId: {canonical_id}")
        indexed[canonical_id] = source
    return indexed


def _parser_coverage_required(source: dict[str, Any]) -> bool:
    canonical_id = source.get("canonicalId", "<unknown>")
    enrollment = source.get("compatibilityEnrollment")
    if enrollment is None:
        # Backward-compatible legacy behavior. New enrollments are explicit PENDING,
        # while migrated release-gate members are explicit ACTIVE.
        return True
    if not isinstance(enrollment, dict):
        raise ParserFamilyPlanError(f"{canonical_id}: compatibilityEnrollment must be an object")

    state = enrollment.get("state")
    required = enrollment.get("parserCoverageRequired")
    if state not in {"PENDING", "ACTIVE"}:
        raise ParserFamilyPlanError(
            f"{canonical_id}: compatibilityEnrollment.state must be PENDING or ACTIVE"
        )
    if not isinstance(required, bool):
        raise ParserFamilyPlanError(
            f"{canonical_id}: compatibilityEnrollment.parserCoverageRequired must be boolean"
        )
    if state == "PENDING" and required:
        raise ParserFamilyPlanError(
            f"{canonical_id}: PENDING enrollment cannot require parser coverage"
        )
    if state == "ACTIVE" and not required:
        raise ParserFamilyPlanError(
            f"{canonical_id}: ACTIVE enrollment must require parser coverage"
        )
    return required


def _require_true(document: dict[str, Any], key: str) -> None:
    if document.get(key) is not True:
        raise ParserFamilyPlanError(f"policies.{key} must be true")


def validate_plan(plan: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    if plan.get("schemaVersion") != 1:
        raise ParserFamilyPlanError("schemaVersion must be 1")

    policies = plan.get("policies")
    if not isinstance(policies, dict):
        raise ParserFamilyPlanError("policies must be an object")
    for key in (
        "declarativeOnboarding",
        "failClosed",
        "requireRegistryMembership",
        "duplicateMembershipForbidden",
        "realParserExecutionRequired",
    ):
        _require_true(policies, key)

    scope = registry.get("scope")
    providers = set(scope.get("providers", [])) if isinstance(scope, dict) else set()
    if not providers:
        raise ParserFamilyPlanError("registry.scope.providers must be non-empty")
    sources = _registry_sources(registry)

    required_sources = {
        canonical_id: source
        for canonical_id, source in sources.items()
        if _parser_coverage_required(source)
    }
    required_memberships = {
        (provider, canonical_id)
        for canonical_id, source in required_sources.items()
        for provider in source.get("providers", [])
    }

    families = plan.get("families")
    if not isinstance(families, list) or not families:
        raise ParserFamilyPlanError("families must be a non-empty list")

    family_ids: set[str] = set()
    memberships: set[tuple[str, str]] = set()
    provider_counts: dict[str, int] = {provider: 0 for provider in sorted(providers)}

    for family in families:
        if not isinstance(family, dict):
            raise ParserFamilyPlanError("family entries must be objects")
        family_id = family.get("id")
        provider = family.get("provider")
        adapter_family = family.get("registryAdapterFamily")
        parser_family = family.get("providerParserFamily")
        runner = family.get("runner")

        if not isinstance(family_id, str) or not family_id:
            raise ParserFamilyPlanError("family.id must be a non-empty string")
        if family_id in family_ids:
            raise ParserFamilyPlanError(f"duplicate family id: {family_id}")
        family_ids.add(family_id)
        if provider not in providers:
            raise ParserFamilyPlanError(f"{family_id}: unknown provider {provider!r}")
        if not isinstance(adapter_family, str) or not adapter_family:
            raise ParserFamilyPlanError(f"{family_id}: registryAdapterFamily is required")
        if not isinstance(parser_family, str) or not parser_family:
            raise ParserFamilyPlanError(f"{family_id}: providerParserFamily is required")
        if not isinstance(runner, str) or not runner:
            raise ParserFamilyPlanError(f"{family_id}: runner is required")

        members = family.get("members")
        if not isinstance(members, list) or not members:
            raise ParserFamilyPlanError(f"{family_id}: members must be a non-empty list")

        for member in members:
            if not isinstance(member, dict):
                raise ParserFamilyPlanError(f"{family_id}: member must be an object")
            canonical_id = member.get("canonicalId")
            test_class = member.get("testClass")
            if canonical_id not in sources:
                raise ParserFamilyPlanError(f"{family_id}: unknown canonicalId {canonical_id!r}")
            if not isinstance(test_class, str) or not test_class:
                raise ParserFamilyPlanError(f"{family_id}/{canonical_id}: testClass is required")

            source = sources[canonical_id]
            if provider not in source.get("providers", []):
                raise ParserFamilyPlanError(
                    f"{family_id}/{canonical_id}: provider {provider} is not a registry membership"
                )
            if source.get("adapterFamily") != adapter_family:
                raise ParserFamilyPlanError(
                    f"{family_id}/{canonical_id}: registry adapter family mismatch; "
                    f"expected {source.get('adapterFamily')!r}, plan has {adapter_family!r}"
                )

            membership = (provider, canonical_id)
            if membership in memberships:
                raise ParserFamilyPlanError(
                    f"duplicate parser execution membership: {provider}/{canonical_id}"
                )
            memberships.add(membership)
            provider_counts[provider] += 1

            identity = source.get("upstreamIdentities", {}).get(provider, {})
            module = member.get("module")
            if module is not None:
                if not isinstance(module, str) or not module:
                    raise ParserFamilyPlanError(f"{family_id}/{canonical_id}: module must be non-empty")
                if identity.get("module") != module:
                    raise ParserFamilyPlanError(
                        f"{family_id}/{canonical_id}: module {module!r} does not match registry "
                        f"identity {identity.get('module')!r}"
                    )

            runtime_profile = member.get("runtimeProfile", "common")
            if not isinstance(runtime_profile, str) or not runtime_profile:
                raise ParserFamilyPlanError(
                    f"{family_id}/{canonical_id}: runtimeProfile must be a non-empty string"
                )
            if provider != "keiyoushi" and runtime_profile != "common":
                raise ParserFamilyPlanError(
                    f"{family_id}/{canonical_id}: runtimeProfile is only supported for keiyoushi"
                )

            repair_recipes = member.get("repairRecipes", [])
            if not isinstance(repair_recipes, list) or any(
                not isinstance(recipe, str) or not recipe for recipe in repair_recipes
            ):
                raise ParserFamilyPlanError(
                    f"{family_id}/{canonical_id}: repairRecipes must be non-empty strings"
                )

    missing_required = sorted(required_memberships - memberships)
    if missing_required:
        rendered = ", ".join(f"{canonical_id}@{provider}" for provider, canonical_id in missing_required)
        raise ParserFamilyPlanError(
            f"ACTIVE registry membership(s) missing real parser family coverage: {rendered}"
        )

    unexpected = sorted(memberships - required_memberships)
    if unexpected:
        rendered = ", ".join(f"{canonical_id}@{provider}" for provider, canonical_id in unexpected)
        raise ParserFamilyPlanError(
            f"parser family coverage references PENDING/non-required membership(s): {rendered}"
        )

    return {
        "schemaVersion": 1,
        "familyCount": len(family_ids),
        "membershipCount": len(memberships),
        "requiredSourceCount": len(required_sources),
        "pendingSourceCount": len(sources) - len(required_sources),
        "requiredMembershipCount": len(required_memberships),
        "providerMembershipCounts": provider_counts,
        "status": "VALID",
    }


def execution_plan(
    plan: dict[str, Any],
    registry: dict[str, Any],
    provider: str | None = None,
) -> dict[str, Any]:
    summary = validate_plan(plan, registry)
    registry_providers = set(registry["scope"]["providers"])
    if provider is not None and provider not in registry_providers:
        raise ParserFamilyPlanError(f"unknown provider: {provider}")

    include: list[dict[str, Any]] = []
    for family in plan["families"]:
        if provider is not None and family["provider"] != provider:
            continue
        for member in family["members"]:
            entry = {
                "provider": family["provider"],
                "familyId": family["id"],
                "registryAdapterFamily": family["registryAdapterFamily"],
                "providerParserFamily": family["providerParserFamily"],
                "runner": family["runner"],
                "canonicalId": member["canonicalId"],
                "testClass": member["testClass"],
                "runtimeProfile": member.get("runtimeProfile", "common"),
                "repairRecipes": member.get("repairRecipes", []),
            }
            if "module" in member:
                entry["module"] = member["module"]
            include.append(entry)

    include.sort(key=lambda item: (item["provider"], item["familyId"], item["canonicalId"]))
    return {
        "schemaVersion": 1,
        "provider": provider or "ALL",
        "familyCount": len({item["familyId"] for item in include}),
        "membershipCount": len(include),
        "validatedTotalMembershipCount": summary["membershipCount"],
        "requiredSourceCount": summary["requiredSourceCount"],
        "pendingSourceCount": summary["pendingSourceCount"],
        "include": include,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="compatibility/source-registry.json")
    parser.add_argument("--families", default="compatibility/parser-families.json")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate ACTIVE registry coverage and family execution metadata")
    validate.add_argument("--output")

    plan = sub.add_parser("plan", help="emit a provider matrix for CI")
    plan.add_argument("--provider", choices=["uma", "gekkoushi", "keiyoushi"])
    plan.add_argument("--output")
    return parser


def _emit(document: dict[str, Any], output: str | None) -> None:
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


def main() -> int:
    args = build_parser().parse_args()
    registry = load_json(args.registry)
    families = load_json(args.families)
    if args.command == "validate":
        _emit(validate_plan(families, registry), args.output)
        return 0
    if args.command == "plan":
        _emit(execution_plan(families, registry, args.provider), args.output)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
