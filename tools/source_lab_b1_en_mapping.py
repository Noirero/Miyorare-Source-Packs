#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
PRIMARY = ("uma", "gekkoushi")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def provider_identity(provider: str, mapping: dict[str, Any]) -> str:
    if provider == "keiyoushi":
        return f"module:{mapping.get('module', '')}|sourceId:{mapping.get('sourceId', '')}"
    return f"file:{mapping.get('file', '')}|sourceName:{mapping.get('sourceName', '')}"


def provider_combo(providers: dict[str, Any]) -> str:
    ordered = [p for p in PROVIDERS if p in providers]
    return "+".join(ordered)


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


def build_report(
    inventory: dict[str, Any],
    farm: dict[str, Any],
    aliases: dict[str, Any],
    upstream_registry: dict[str, Any],
    status: dict[str, Any],
    *,
    inventory_commit: str = "",
    foundation_commit: str = "",
    miyorare_commit: str = "",
) -> dict[str, Any]:
    if inventory.get("kind") != "MIYORARE_SOURCE_INVENTORY" or inventory.get("informationalOnly") is not True:
        raise ValueError("inventory is not informational Miyorare source inventory")
    inv_sources = inventory.get("sources")
    farm_sources = farm.get("sources")
    if not isinstance(inv_sources, list) or not isinstance(farm_sources, list):
        raise ValueError("inventory/farm sources must be lists")

    inv_en = [s for s in inv_sources if isinstance(s, dict) and s.get("language") == "en"]
    farm_en = [s for s in farm_sources if isinstance(s, dict) and s.get("language") == "en"]
    inv_by_id = {s.get("canonicalId"): s for s in inv_en if isinstance(s.get("canonicalId"), str)}
    farm_by_id = {s.get("canonicalId"): s for s in farm_en if isinstance(s.get("canonicalId"), str)}
    if len(inv_by_id) != len(inv_en):
        raise ValueError("duplicate or invalid EN canonicalId in inventory")
    if len(farm_by_id) != len(farm_en):
        raise ValueError("duplicate or invalid EN canonicalId in farm")

    combo_counts: Counter[str] = Counter()
    provider_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    primary_covered: list[str] = []
    reference_only: list[str] = []
    primary_overlap: list[str] = []
    primary_with_reference: list[str] = []
    inventory_attention: list[dict[str, Any]] = []

    for source in inv_en:
        providers = source.get("providers") if isinstance(source.get("providers"), dict) else {}
        combo_counts[provider_combo(providers)] += 1
        for provider in providers:
            if provider in PROVIDERS:
                provider_counts[provider] += 1
        confidence_counts[str(source.get("identityConfidence") or "unknown")] += 1
        cid = str(source["canonicalId"])
        has_primary = any(p in providers for p in PRIMARY)
        if has_primary:
            primary_covered.append(cid)
        if set(providers) == {"keiyoushi"}:
            reference_only.append(cid)
        if all(p in providers for p in PRIMARY):
            primary_overlap.append(cid)
        if has_primary and "keiyoushi" in providers:
            primary_with_reference.append(cid)
        if source.get("needsAttention"):
            inventory_attention.append({
                "canonicalId": cid,
                "displayName": source.get("displayName"),
                "reasons": source.get("attentionReasons", []),
                "providers": sorted(providers),
            })

    farm_state_counts: Counter[str] = Counter()
    for source in farm_en:
        enrollment = source.get("compatibilityEnrollment")
        state = enrollment.get("state") if isinstance(enrollment, dict) else None
        farm_state_counts[str(state or "UNKNOWN")] += 1

    inventory_missing_from_farm = sorted(set(inv_by_id) - set(farm_by_id))
    farm_missing_from_inventory = sorted(set(farm_by_id) - set(inv_by_id))

    farm_provider_not_discovered: list[dict[str, str]] = []
    provider_identity_drift: list[dict[str, str]] = []
    discovered_provider_not_enrolled: list[dict[str, str]] = []
    for cid in sorted(set(inv_by_id) & set(farm_by_id)):
        inv_p = inv_by_id[cid].get("providers") if isinstance(inv_by_id[cid].get("providers"), dict) else {}
        farm_identities = farm_by_id[cid].get("upstreamIdentities") if isinstance(farm_by_id[cid].get("upstreamIdentities"), dict) else {}
        farm_memberships = set(farm_by_id[cid].get("providers") or []) | set(farm_identities)
        for provider in sorted(farm_memberships & set(PROVIDERS)):
            mapping = farm_identities.get(provider)
            if provider not in inv_p:
                farm_provider_not_discovered.append({"canonicalId": cid, "provider": provider})
            elif isinstance(mapping, dict):
                expected = provider_identity(provider, mapping)
                actual = provider_identity(provider, inv_p[provider])
                if expected != actual:
                    provider_identity_drift.append({
                        "canonicalId": cid,
                        "provider": provider,
                        "farmIdentity": expected,
                        "inventoryIdentity": actual,
                    })
        for provider in sorted((set(inv_p) & set(PROVIDERS)) - farm_memberships):
            discovered_provider_not_enrolled.append({"canonicalId": cid, "provider": provider})

    official_en = []
    official_missing_inventory: list[str] = []
    official_missing_farm: list[str] = []
    official_identity_drift: list[dict[str, str]] = []
    for item in aliases.get("aliases", []):
        if not isinstance(item, dict) or item.get("language") != "en" or not isinstance(item.get("canonicalId"), str):
            continue
        cid = item["canonicalId"]
        declared = [p for p in PROVIDERS if isinstance(item.get(p), dict)]
        official = item.get("official") if isinstance(item.get("official"), dict) else {}
        row = {
            "canonicalId": cid,
            "sourceName": official.get("sourceName"),
            "verifiedDomain": item.get("verifiedDomain"),
            "declaredProviders": declared,
            "inventoryPresent": cid in inv_by_id,
            "farmPresent": cid in farm_by_id,
        }
        official_en.append(row)
        if cid not in inv_by_id:
            official_missing_inventory.append(cid)
        if cid not in farm_by_id:
            official_missing_farm.append(cid)
        if cid in inv_by_id:
            inv_p = inv_by_id[cid].get("providers") if isinstance(inv_by_id[cid].get("providers"), dict) else {}
            for provider in declared:
                if provider not in inv_p:
                    official_identity_drift.append({"canonicalId": cid, "provider": provider, "reason": "DECLARED_PROVIDER_NOT_DISCOVERED"})
                    continue
                expected = provider_identity(provider, item[provider])
                actual = provider_identity(provider, inv_p[provider])
                if expected != actual:
                    official_identity_drift.append({
                        "canonicalId": cid,
                        "provider": provider,
                        "reason": "IDENTITY_DRIFT",
                        "declaredIdentity": expected,
                        "inventoryIdentity": actual,
                    })

    provider_relations: dict[str, Any] = {}
    snapshots = inventory.get("providerSnapshots") if isinstance(inventory.get("providerSnapshots"), dict) else {}
    status_providers = status.get("providers") if isinstance(status.get("providers"), dict) else {}
    candidates = ((status.get("automation") or {}).get("candidates") or {}) if isinstance(status.get("automation"), dict) else {}
    registry_providers = upstream_registry.get("providers") if isinstance(upstream_registry.get("providers"), dict) else {}
    for provider in PROVIDERS:
        snap = str((snapshots.get(provider) or {}).get("commit") or "")
        st = status_providers.get(provider) if isinstance(status_providers.get(provider), dict) else {}
        reg = registry_providers.get(provider) if isinstance(registry_providers.get(provider), dict) else {}
        cand = candidates.get(provider) if isinstance(candidates.get(provider), dict) else {}
        active = str(st.get("activeCommit") or "")
        lkg = str(st.get("lastKnownGood") or reg.get("lastKnownGood") or "")
        candidate = str(cand.get("candidate") or "") or None
        provider_relations[provider] = {
            "inventorySnapshot": snap,
            "activeCommit": active,
            "lastKnownGood": lkg,
            "farmCandidate": candidate,
            "relation": classify_snapshot(snap, active, lkg, candidate),
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
        "referenceOnlyKeiyoushi": reference_only,
    }

    structural_attention = (
        len(inventory_attention)
        + len(farm_missing_from_inventory)
        + len(farm_provider_not_discovered)
        + len(provider_identity_drift)
        + len(official_missing_inventory)
        + len(official_missing_farm)
        + len(official_identity_drift)
    )

    return {
        "phase": "TRACK_B_BATCH_1_EN_AUDIT_MAPPING",
        "status": "COMPLETE_WITH_FINDINGS" if structural_attention else "COMPLETE",
        "readOnly": True,
        "authority": {
            "inventoryRole": "INFORMATIONAL_DISCOVERY_ONLY",
            "farmRole": "OPERATIONAL_LKG_AND_LIFECYCLE_AUTHORITY",
            "keiyoushiRole": "REFERENCE_RECOVERY_COMPARISON_ONLY",
            "primaryProviders": list(PRIMARY),
        },
        "provenance": {
            "inventoryCommit": inventory_commit,
            "foundationCommit": foundation_commit,
            "miyorareCommit": miyorare_commit,
            "providerSnapshots": snapshots,
        },
        "summary": {
            "inventoryAllSources": inventory.get("stats", {}).get("allSources"),
            "inventoryEnSources": len(inv_en),
            "inventoryEnProviderMappings": sum(provider_counts.values()),
            "farmEnSources": len(farm_en),
            "farmEnEnrollmentStates": dict(sorted(farm_state_counts.items())),
            "primaryCoveredSources": len(primary_covered),
            "referenceOnlyKeiyoushiSources": len(reference_only),
            "primaryOverlapUmaGekkoushiSources": len(primary_overlap),
            "primarySourcesWithKeiyoushiReference": len(primary_with_reference),
            "officialMiyorareEnAliases": len(official_en),
            "inventoryNeedsAttention": len(inventory_attention),
            "structuralAttentionCount": structural_attention,
        },
        "inventoryProviderCounts": {p: provider_counts[p] for p in PROVIDERS},
        "inventoryProviderCombinationCounts": dict(sorted(combo_counts.items())),
        "identityConfidenceCounts": dict(sorted(confidence_counts.items())),
        "providerSnapshotRelations": provider_relations,
        "officialMiyorareEnAliases": official_en,
        "findings": findings,
    }


def markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Track B Batch 1 — EN Audit & Mapping",
        "",
        f"Status: **{report['status']}**",
        "",
        "This report is read-only. `source-inventory-live` is discovery data; Compatibility Farm remains the operational LKG/lifecycle authority.",
        "",
        "## Summary",
        "",
        f"- Inventory EN canonical sources: **{s['inventoryEnSources']}**",
        f"- EN provider mappings: **{s['inventoryEnProviderMappings']}**",
        f"- Farm EN sources: **{s['farmEnSources']}**",
        f"- Covered by UMA or Gekkoushi: **{s['primaryCoveredSources']}**",
        f"- Keiyoushi-only reference sources: **{s['referenceOnlyKeiyoushiSources']}**",
        f"- UMA + Gekkoushi overlap: **{s['primaryOverlapUmaGekkoushiSources']}**",
        f"- Primary sources also represented in Keiyoushi: **{s['primarySourcesWithKeiyoushiReference']}**",
        f"- Official Miyorare EN aliases: **{s['officialMiyorareEnAliases']}**",
        f"- Inventory identity entries needing attention: **{s['inventoryNeedsAttention']}**",
        f"- Structural attention findings: **{s['structuralAttentionCount']}**",
        "",
        "## Provider combinations",
        "",
    ]
    for combo, count in report["inventoryProviderCombinationCounts"].items():
        lines.append(f"- `{combo or 'none'}`: {count}")
    lines += ["", "## Provider snapshot relation to Farm", ""]
    for provider, row in report["providerSnapshotRelations"].items():
        lines.append(
            f"- **{provider}**: `{row['relation']}` — inventory `{row['inventorySnapshot']}`, "
            f"active/LKG `{row['activeCommit']}`, candidate `{row['farmCandidate'] or 'none'}`"
        )
    lines += ["", "## Official EN aliases", ""]
    for row in report["officialMiyorareEnAliases"]:
        lines.append(
            f"- `{row['canonicalId']}` — domain `{row.get('verifiedDomain') or 'unknown'}`, "
            f"providers `{', '.join(row['declaredProviders']) or 'none'}`, inventory={row['inventoryPresent']}, farm={row['farmPresent']}"
        )
    lines += ["", "## Finding counts", ""]
    for key, value in report["findings"].items():
        lines.append(f"- `{key}`: {len(value)}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--farm-registry", type=Path, required=True)
    parser.add_argument("--aliases", type=Path, required=True)
    parser.add_argument("--upstream-registry", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--inventory-commit", default="")
    parser.add_argument("--foundation-commit", default="")
    parser.add_argument("--miyorare-commit", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(
        load_json(args.inventory),
        load_json(args.farm_registry),
        load_json(args.aliases),
        load_json(args.upstream_registry),
        load_json(args.status),
        inventory_commit=args.inventory_commit,
        foundation_commit=args.foundation_commit,
        miyorare_commit=args.miyorare_commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
