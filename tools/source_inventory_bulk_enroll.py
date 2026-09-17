#!/usr/bin/env python3
"""Enroll safe ID/EN inventory sources into the Compatibility Farm as PENDING.

This mutates only a supplied registry file. It never activates parser coverage and never
publishes. Provider baseline path lists are supplied by the caller so inventory entries that
do not exist at the authoritative Farm baseline remain held.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

LANGUAGES = {"id", "en"}
PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
CAPABILITIES = [
    "load", "browse", "search", "details", "chapters",
    "content", "authenticate", "download", "reader",
]


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def identity_for(provider: str, mapping: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    identity = {
        key: mapping[key]
        for key in ("sourceName", "module", "file", "sourceId")
        if key in mapping and mapping[key] not in (None, "")
    }
    if not identity.get("sourceName"):
        return None
    if provider == "keiyoushi" and isinstance(identity.get("module"), str):
        return identity, f"{identity['module']}/build.gradle.kts"
    if provider in {"uma", "gekkoushi"} and isinstance(identity.get("file"), str):
        return identity, identity["file"]
    return None


def enroll(
    inventory: dict[str, Any],
    registry: dict[str, Any],
    baseline_paths: dict[str, set[str]],
    *,
    inventory_commit: str,
    foundation_commit: str,
    workflow_run_id: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if inventory.get("schemaVersion") != 1 or inventory.get("kind") != "MIYORARE_SOURCE_INVENTORY":
        raise ValueError("invalid source inventory schema")
    if inventory.get("informationalOnly") is not True:
        raise ValueError("source inventory trust boundary is invalid")
    if registry.get("schemaVersion") != 1:
        raise ValueError("invalid Farm registry schema")

    scope = registry.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("Farm scope is missing")
    configured_languages = {str(v).lower() for v in scope.get("languages", [])}
    if not LANGUAGES.issubset(configured_languages):
        raise ValueError("Farm language contract must include id and en")

    baselines = registry.get("providerBaselines")
    if not isinstance(baselines, dict):
        raise ValueError("provider baselines are missing")
    for provider in PROVIDERS:
        baseline = baselines.get(provider)
        if not isinstance(baseline, str) or len(baseline) != 40:
            raise ValueError(f"invalid {provider} baseline")
        if provider not in baseline_paths:
            raise ValueError(f"missing {provider} baseline path set")

    sources = registry.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Farm registry sources is invalid")
    existing: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("canonicalId"), str):
            raise ValueError("invalid existing Farm source")
        canonical = source["canonicalId"]
        if canonical in existing:
            raise ValueError(f"duplicate existing canonicalId: {canonical}")
        existing[canonical] = source

    defaults = registry.get("defaults") if isinstance(registry.get("defaults"), dict) else {}
    repair = deepcopy(defaults.get("repairPolicy")) if isinstance(defaults.get("repairPolicy"), dict) else {
        "autoDiagnose": True,
        "safeSelfRepair": True,
        "keepLastKnownGood": True,
        "validatedCanonicalFallback": True,
        "holdRequiresOwnerAction": False,
    }

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "languages": ["id", "en"],
        "inventoryCommit": inventory_commit,
        "foundationBefore": foundation_commit,
        "inventoryMatched": 0,
        "alreadyEnrolled": 0,
        "enrolled": 0,
        "skippedNeedsAttention": 0,
        "skippedInvalidProviderIdentity": 0,
        "skippedMissingAtBaseline": 0,
        "skippedDuplicateInventoryCanonical": 0,
        "examples": {"missingAtBaseline": [], "invalidProviderIdentity": []},
    }

    inventory_by_canonical: dict[str, dict[str, Any] | None] = {}
    for item in inventory.get("sources", []):
        if not isinstance(item, dict) or str(item.get("language") or "").lower() not in LANGUAGES:
            continue
        report["inventoryMatched"] += 1
        canonical = item.get("canonicalId")
        if not isinstance(canonical, str) or not canonical:
            report["skippedInvalidProviderIdentity"] += 1
            continue
        if canonical not in inventory_by_canonical:
            inventory_by_canonical[canonical] = item
        elif inventory_by_canonical[canonical] != item:
            report["skippedDuplicateInventoryCanonical"] += 1
            inventory_by_canonical[canonical] = None

    for canonical in sorted(inventory_by_canonical):
        item = inventory_by_canonical[canonical]
        if item is None:
            continue
        if canonical in existing:
            report["alreadyEnrolled"] += 1
            continue
        if item.get("needsAttention") is True:
            report["skippedNeedsAttention"] += 1
            continue

        mappings = item.get("providers")
        if not isinstance(mappings, dict) or not mappings:
            report["skippedInvalidProviderIdentity"] += 1
            continue

        identities: dict[str, dict[str, Any]] = {}
        current: dict[str, str] = {}
        invalid = False
        missing = False
        for provider in sorted(mappings):
            mapping = mappings[provider]
            if provider not in PROVIDERS or not isinstance(mapping, dict) or mapping.get("available") is False:
                invalid = True
                break
            resolved = identity_for(provider, mapping)
            if resolved is None:
                invalid = True
                break
            identity, check_path = resolved
            if check_path not in baseline_paths[provider]:
                missing = True
                break
            identities[provider] = identity
            current[provider] = baselines[provider]

        if invalid:
            report["skippedInvalidProviderIdentity"] += 1
            if len(report["examples"]["invalidProviderIdentity"]) < 20:
                report["examples"]["invalidProviderIdentity"].append(canonical)
            continue
        if missing:
            report["skippedMissingAtBaseline"] += 1
            if len(report["examples"]["missingAtBaseline"]) < 20:
                report["examples"]["missingAtBaseline"].append(canonical)
            continue

        language = str(item.get("language")).lower()
        new_source = {
            "canonicalId": canonical,
            "displayName": item.get("displayName") or canonical.rsplit(":", 1)[-1],
            "language": language,
            "contentProfile": "manga",
            "authType": "UNSUPPORTED",
            "adapterFamily": "unclassified",
            "compatibilityEnrollment": {"state": "PENDING", "parserCoverageRequired": False},
            "providers": sorted(identities),
            "upstreamIdentities": identities,
            "currentVersion": dict(current),
            "lastKnownGood": dict(current),
            "healthyHistory": [],
            "updateState": "PROMOTED",
            "runtimeHealth": "UNKNOWN",
            "approvalState": "NOT_READY",
            "ownerActionRequired": False,
            "publishEligible": False,
            "protectedOverlays": [],
            "compatibilityBaseline": {"status": "PENDING", "capabilities": list(CAPABILITIES)},
            "repairPolicy": deepcopy(repair),
            "selectionReasons": ["automatic-source-inventory", "language-scope-id-en"],
            "enrollmentEvidence": {
                "inventoryCommit": inventory_commit,
                "foundationBefore": foundation_commit,
                "workflowRunId": workflow_run_id,
            },
        }
        sources.append(new_source)
        existing[canonical] = new_source
        report["enrolled"] += 1

    sources.sort(key=lambda item: (
        str(item.get("language", "")),
        str(item.get("displayName", "")).casefold(),
        str(item.get("canonicalId", "")),
    ))
    scope["targetSize"] = len(sources)
    scope["enrollmentMode"] = "inventory-managed-id-en"
    scope["autoEnrollmentLanguages"] = ["id", "en"]
    scope["autoEnrollmentState"] = "PENDING"
    report["registrySizeAfter"] = len(sources)
    return registry, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--inventory-commit", required=True)
    parser.add_argument("--foundation-commit", required=True)
    parser.add_argument("--workflow-run-id", type=int, default=0)
    parser.add_argument("--baseline-paths", action="append", required=True, metavar="PROVIDER=FILE")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    baseline_paths: dict[str, set[str]] = {}
    for raw in args.baseline_paths:
        provider, sep, filename = raw.partition("=")
        if not sep or provider not in PROVIDERS:
            raise SystemExit(f"invalid --baseline-paths: {raw}")
        baseline_paths[provider] = set(Path(filename).read_text(encoding="utf-8").splitlines())

    registry, report = enroll(
        load_json(args.inventory),
        load_json(args.registry),
        baseline_paths,
        inventory_commit=args.inventory_commit,
        foundation_commit=args.foundation_commit,
        workflow_run_id=args.workflow_run_id,
    )
    write_json(args.registry, registry)
    write_json(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
