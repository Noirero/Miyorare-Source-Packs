#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
LANGUAGE = "id"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def provider_identity(provider: str, mapping: dict[str, Any]) -> str:
    if provider == "keiyoushi":
        return f"module:{mapping.get('module', '')}|sourceId:{mapping.get('sourceId', '')}"
    return f"file:{mapping.get('file', '')}|sourceName:{mapping.get('sourceName', '')}"


def classify_snapshot(snapshot: str, active: str, lkg: str, candidate: str | None) -> str:
    if snapshot and snapshot == active == lkg:
        return "ACTIVE_LKG"
    if candidate and snapshot == candidate:
        return "FARM_CANDIDATE"
    if snapshot and snapshot == active:
        return "ACTIVE_NON_LKG"
    if snapshot and snapshot == lkg:
        return "LKG_NON_ACTIVE"
    return "UNTRACKED_BY_FARM_STATUS"


def canonical_map(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        canonical = row.get("canonicalId")
        if not isinstance(canonical, str):
            raise ValueError(f"{label} has invalid canonicalId")
        if canonical in result:
            raise ValueError(f"duplicate {label} canonicalId: {canonical}")
        result[canonical] = row
    return result


def build_report(
    inventory: dict[str, Any],
    farm: dict[str, Any],
    aliases: dict[str, Any],
    packs: dict[str, Any],
    upstream_registry: dict[str, Any],
    status: dict[str, Any],
    *,
    inventory_commit: str = "",
    foundation_commit: str = "",
    miyorare_commit: str = "",
) -> dict[str, Any]:
    if inventory.get("kind") != "MIYORARE_SOURCE_INVENTORY" or inventory.get("informationalOnly") is not True:
        raise ValueError("inventory must be informational Miyorare source inventory")
    inv_rows = inventory.get("sources")
    farm_rows = farm.get("sources")
    if not isinstance(inv_rows, list) or not isinstance(farm_rows, list):
        raise ValueError("inventory/farm sources must be lists")

    inv_id = [row for row in inv_rows if isinstance(row, dict) and row.get("language") == LANGUAGE]
    farm_id = [row for row in farm_rows if isinstance(row, dict) and row.get("language") == LANGUAGE]
    inv_by_id = canonical_map(inv_id, "inventory ID")
    farm_by_id = canonical_map(farm_id, "farm ID")

    provider_counts: Counter[str] = Counter()
    combo_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    inventory_attention: list[dict[str, Any]] = []
    for source in inv_id:
        providers = source.get("providers") if isinstance(source.get("providers"), dict) else {}
        present = [provider for provider in PROVIDERS if provider in providers]
        combo_counts["+".join(present)] += 1
        for provider in present:
            provider_counts[provider] += 1
        confidence_counts[str(source.get("identityConfidence") or "unknown")] += 1
        if source.get("needsAttention"):
            inventory_attention.append({
                "canonicalId": source["canonicalId"],
                "displayName": source.get("displayName"),
                "providers": present,
                "reasons": source.get("attentionReasons", []),
            })

    farm_states: Counter[str] = Counter()
    for source in farm_id:
        enrollment = source.get("compatibilityEnrollment")
        state = enrollment.get("state") if isinstance(enrollment, dict) else None
        farm_states[str(state or "UNKNOWN")] += 1

    inventory_missing_from_farm = sorted(set(inv_by_id) - set(farm_by_id))
    farm_missing_from_inventory = sorted(set(farm_by_id) - set(inv_by_id))
    farm_provider_not_discovered: list[dict[str, str]] = []
    provider_identity_drift: list[dict[str, str]] = []
    discovered_provider_not_enrolled: list[dict[str, str]] = []
    for canonical in sorted(set(inv_by_id) & set(farm_by_id)):
        inv_providers = inv_by_id[canonical].get("providers") if isinstance(inv_by_id[canonical].get("providers"), dict) else {}
        farm_identities = farm_by_id[canonical].get("upstreamIdentities") if isinstance(farm_by_id[canonical].get("upstreamIdentities"), dict) else {}
        farm_memberships = set(farm_by_id[canonical].get("providers") or []) | set(farm_identities)
        for provider in sorted(farm_memberships & set(PROVIDERS)):
            if provider not in inv_providers:
                farm_provider_not_discovered.append({"canonicalId": canonical, "provider": provider})
                continue
            mapping = farm_identities.get(provider)
            if isinstance(mapping, dict):
                expected = provider_identity(provider, mapping)
                actual = provider_identity(provider, inv_providers[provider])
                if expected != actual:
                    provider_identity_drift.append({
                        "canonicalId": canonical,
                        "provider": provider,
                        "farmIdentity": expected,
                        "inventoryIdentity": actual,
                    })
        for provider in sorted((set(inv_providers) & set(PROVIDERS)) - farm_memberships):
            discovered_provider_not_enrolled.append({"canonicalId": canonical, "provider": provider})

    official_rows: list[dict[str, Any]] = []
    official_missing_inventory: list[str] = []
    official_missing_farm: list[str] = []
    official_identity_drift: list[dict[str, str]] = []
    for item in aliases.get("aliases", []):
        if not isinstance(item, dict) or item.get("language") != LANGUAGE or not isinstance(item.get("canonicalId"), str):
            continue
        canonical = item["canonicalId"]
        declared = [provider for provider in PROVIDERS if isinstance(item.get(provider), dict)]
        official = item.get("official") if isinstance(item.get("official"), dict) else {}
        official_rows.append({
            "canonicalId": canonical,
            "sourceName": official.get("sourceName"),
            "verifiedDomain": item.get("verifiedDomain"),
            "declaredProviders": declared,
            "inventoryPresent": canonical in inv_by_id,
            "farmPresent": canonical in farm_by_id,
        })
        if canonical not in inv_by_id:
            official_missing_inventory.append(canonical)
        if canonical not in farm_by_id:
            official_missing_farm.append(canonical)
        if canonical in inv_by_id:
            inv_providers = inv_by_id[canonical].get("providers") if isinstance(inv_by_id[canonical].get("providers"), dict) else {}
            for provider in declared:
                if provider not in inv_providers:
                    official_identity_drift.append({"canonicalId": canonical, "provider": provider, "reason": "DECLARED_PROVIDER_NOT_DISCOVERED"})
                elif provider_identity(provider, item[provider]) != provider_identity(provider, inv_providers[provider]):
                    official_identity_drift.append({"canonicalId": canonical, "provider": provider, "reason": "IDENTITY_DRIFT"})

    pack_table = packs.get("packs")
    if not isinstance(pack_table, dict) or not isinstance(pack_table.get(LANGUAGE), dict):
        raise ValueError("Miyorare packs.json has no ID pack")
    id_pack = pack_table[LANGUAGE]
    if id_pack.get("pluginId") != "miyorare-id" or id_pack.get("language") != LANGUAGE:
        raise ValueError("unexpected Miyorare ID pack identity")
    curated_uma = id_pack.get("sources")
    if not isinstance(curated_uma, list) or any(not isinstance(value, str) for value in curated_uma):
        raise ValueError("ID pack sources must be a string list")
    if len(curated_uma) != len(set(curated_uma)):
        raise ValueError("ID pack has duplicate curated UMA sources")
    expected_uma_paths = {f"src/main/kotlin/tsuki/site/id/{value.lstrip('/')}" for value in curated_uma}
    discovered_uma_paths: set[str] = set()
    discovered_gekkoushi = 0
    discovered_keiyoushi = 0
    for source in inv_id:
        providers = source.get("providers") if isinstance(source.get("providers"), dict) else {}
        uma = providers.get("uma")
        if isinstance(uma, dict) and isinstance(uma.get("file"), str):
            discovered_uma_paths.add(uma["file"])
        discovered_gekkoushi += int(isinstance(providers.get("gekkoushi"), dict))
        discovered_keiyoushi += int(isinstance(providers.get("keiyoushi"), dict))
    consumer_uma_missing_inventory = sorted(expected_uma_paths - discovered_uma_paths)
    inventory_uma_not_curated = sorted(discovered_uma_paths - expected_uma_paths)
    include_all = id_pack.get("includeAllFrom") if isinstance(id_pack.get("includeAllFrom"), list) else []
    gekkoushi_mode = "INCLUDE_ALL_FROM" if "gekkoushi" in include_all else "NOT_INCLUDE_ALL"

    snapshots = inventory.get("providerSnapshots") if isinstance(inventory.get("providerSnapshots"), dict) else {}
    status_providers = status.get("providers") if isinstance(status.get("providers"), dict) else {}
    candidates = ((status.get("automation") or {}).get("candidates") or {}) if isinstance(status.get("automation"), dict) else {}
    registry_providers = upstream_registry.get("providers") if isinstance(upstream_registry.get("providers"), dict) else {}
    provider_relations: dict[str, Any] = {}
    for provider in PROVIDERS:
        snapshot = str((snapshots.get(provider) or {}).get("commit") or "")
        provider_status = status_providers.get(provider) if isinstance(status_providers.get(provider), dict) else {}
        provider_registry = registry_providers.get(provider) if isinstance(registry_providers.get(provider), dict) else {}
        candidate_row = candidates.get(provider) if isinstance(candidates.get(provider), dict) else {}
        active = str(provider_status.get("activeCommit") or "")
        lkg = str(provider_status.get("lastKnownGood") or provider_registry.get("lastKnownGood") or "")
        candidate = str(candidate_row.get("candidate") or "") or None
        provider_relations[provider] = {
            "inventorySnapshot": snapshot,
            "activeCommit": active,
            "lastKnownGood": lkg,
            "farmCandidate": candidate,
            "relation": classify_snapshot(snapshot, active, lkg, candidate),
        }

    findings = {
        "inventoryNeedsAttention": inventory_attention,
        "farmCanonicalMissingFromInventory": farm_missing_from_inventory,
        "inventoryCanonicalNotEnrolledInFarm": inventory_missing_from_farm,
        "farmProviderNotDiscovered": farm_provider_not_discovered,
        "providerIdentityDrift": provider_identity_drift,
        "discoveredProviderNotEnrolled": discovered_provider_not_enrolled,
        "officialAliasMissingFromInventory": official_missing_inventory,
        "officialAliasMissingFromFarm": official_missing_farm,
        "officialAliasIdentityDrift": official_identity_drift,
        "consumerUmaCuratedPathMissingFromInventory": consumer_uma_missing_inventory,
        "inventoryUmaNotCuratedByConsumer": inventory_uma_not_curated,
    }
    structural_attention = sum(len(findings[key]) for key in (
        "inventoryNeedsAttention",
        "farmCanonicalMissingFromInventory",
        "farmProviderNotDiscovered",
        "providerIdentityDrift",
        "officialAliasMissingFromInventory",
        "officialAliasMissingFromFarm",
        "officialAliasIdentityDrift",
        "consumerUmaCuratedPathMissingFromInventory",
    ))

    packaged = []
    if curated_uma:
        packaged.append("uma")
    if gekkoushi_mode == "INCLUDE_ALL_FROM":
        packaged.append("gekkoushi")
    if "keiyoushi" in include_all:
        packaged.append("keiyoushi")

    return {
        "phase": "TRACK_C_BATCH_1_ID_AUDIT_MAPPING",
        "status": "COMPLETE_WITH_FINDINGS" if structural_attention else "COMPLETE",
        "readOnly": True,
        "language": LANGUAGE,
        "authority": {
            "inventoryRole": "INFORMATIONAL_DISCOVERY_ONLY",
            "farmRole": "OPERATIONAL_LKG_AND_LIFECYCLE_AUTHORITY",
            "consumerRole": "AMAIN2_PACKAGING_CONFIGURATION",
            "providerDecision": "UNDECIDED_PENDING_TRACK_C_CAPABILITY_HEALTH",
            "currentConsumerPackaging": {
                "uma": "CURATED_FILE_LIST",
                "gekkoushi": gekkoushi_mode,
                "keiyoushi": "INCLUDE_ALL_FROM" if "keiyoushi" in include_all else "NOT_DIRECTLY_PACKAGED",
            },
        },
        "provenance": {
            "inventoryCommit": inventory_commit,
            "foundationCommit": foundation_commit,
            "miyorareCommit": miyorare_commit,
            "providerSnapshots": snapshots,
        },
        "summary": {
            "inventoryAllSources": inventory.get("stats", {}).get("allSources"),
            "inventoryIdSources": len(inv_id),
            "inventoryIdProviderMappings": sum(provider_counts.values()),
            "farmIdSources": len(farm_id),
            "farmIdEnrollmentStates": dict(sorted(farm_states.items())),
            "officialMiyorareIdAliases": len(official_rows),
            "consumerUmaCuratedSources": len(curated_uma),
            "consumerUmaCuratedResolved": len(expected_uma_paths) - len(consumer_uma_missing_inventory),
            "consumerGekkoushiDiscoveredSources": discovered_gekkoushi,
            "consumerKeiyoushiReferenceSources": discovered_keiyoushi,
            "inventoryNeedsAttention": len(inventory_attention),
            "structuralAttentionCount": structural_attention,
        },
        "inventoryProviderCounts": {provider: provider_counts[provider] for provider in PROVIDERS},
        "inventoryProviderCombinationCounts": dict(sorted(combo_counts.items())),
        "identityConfidenceCounts": dict(sorted(confidence_counts.items())),
        "providerSnapshotRelations": provider_relations,
        "currentConsumer": {
            "pluginId": id_pack.get("pluginId"),
            "language": id_pack.get("language"),
            "packagedProviders": packaged,
            "gekkoushiMode": gekkoushi_mode,
            "umaCuratedEntries": sorted(curated_uma),
        },
        "officialMiyorareIdAliases": official_rows,
        "findings": findings,
    }


def markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Track C Batch 1 — ID Audit & Mapping",
        "",
        f"Status: **{report['status']}**",
        "",
        "This report is read-only. C1 measures current ID provider coverage and Amain2 packaging; it does not promote a provider role.",
        "",
        "## Summary",
        "",
        f"- Inventory ID canonical sources: **{summary['inventoryIdSources']}**",
        f"- ID provider mappings: **{summary['inventoryIdProviderMappings']}**",
        f"- Farm ID sources: **{summary['farmIdSources']}**",
        f"- Official Miyorare ID aliases: **{summary['officialMiyorareIdAliases']}**",
        f"- Amain2 UMA curated entries resolved: **{summary['consumerUmaCuratedResolved']}/{summary['consumerUmaCuratedSources']}**",
        f"- Gekkoushi ID sources discovered: **{summary['consumerGekkoushiDiscoveredSources']}**",
        f"- Keiyoushi ID references discovered: **{summary['consumerKeiyoushiReferenceSources']}**",
        f"- Structural attention findings: **{summary['structuralAttentionCount']}**",
        "",
        "## Current consumer packaging",
        "",
        f"- Packaged providers: `{', '.join(report['currentConsumer']['packagedProviders']) or 'none'}`",
        f"- Gekkoushi mode: `{report['currentConsumer']['gekkoushiMode']}`",
        "",
        "## Provider combinations",
        "",
    ]
    for combo, count in report["inventoryProviderCombinationCounts"].items():
        lines.append(f"- `{combo or 'none'}`: {count}")
    lines += ["", "## Provider snapshot relation to Farm", ""]
    for provider, row in report["providerSnapshotRelations"].items():
        lines.append(f"- **{provider}**: `{row['relation']}` — inventory `{row['inventorySnapshot']}`, active `{row['activeCommit']}`, LKG `{row['lastKnownGood']}`, candidate `{row['farmCandidate'] or 'none'}`")
    lines += ["", "## Finding counts", ""]
    for key, value in report["findings"].items():
        lines.append(f"- `{key}`: {len(value)}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--farm-registry", type=Path, required=True)
    parser.add_argument("--aliases", type=Path, required=True)
    parser.add_argument("--packs", type=Path, required=True)
    parser.add_argument("--upstream-registry", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--inventory-commit", default="")
    parser.add_argument("--foundation-commit", default="")
    parser.add_argument("--miyorare-commit", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(
        load_json(args.inventory), load_json(args.farm_registry), load_json(args.aliases), load_json(args.packs),
        load_json(args.upstream_registry), load_json(args.status), inventory_commit=args.inventory_commit,
        foundation_commit=args.foundation_commit, miyorare_commit=args.miyorare_commit,
    )
    write_json(args.output, report)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
