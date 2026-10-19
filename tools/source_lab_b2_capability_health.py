#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
PRIMARY = ("uma", "gekkoushi")
HEALTH = {"HEALTHY", "DEGRADED", "HELD", "UNAVAILABLE", "DEPRECATED", "UNKNOWN"}
STRUCTURAL_FINDINGS = (
    "farmCanonicalMissingFromInventory",
    "farmProviderNotDiscovered",
    "providerIdentityDrift",
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def normalize(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def provider_identity(provider: str, mapping: dict[str, Any]) -> str:
    if provider == "keiyoushi":
        return f"module:{mapping.get('module', '')}|sourceId:{mapping.get('sourceId', '')}"
    return f"file:{mapping.get('file', '')}|sourceName:{mapping.get('sourceName', '')}"


def parse_identity(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in value.split("|"):
        if ":" not in part:
            continue
        key, raw = part.split(":", 1)
        result[key] = raw
    return result


def health_rows(source_health: dict[str, Any]) -> list[dict[str, Any]]:
    raw = source_health.get("sources", {})
    if isinstance(raw, dict):
        rows = [dict(value, sourceKey=value.get("sourceKey") or key) for key, value in raw.items() if isinstance(value, dict)]
    elif isinstance(raw, list):
        rows = [dict(value) for value in raw if isinstance(value, dict)]
    else:
        raise ValueError("source health sources must be a mapping or list")
    return rows


def unique_health_match(
    rows: list[dict[str, Any]],
    *,
    canonical_id: str,
    provider: str,
    mapping: dict[str, Any],
    expected_commit: str | None,
) -> dict[str, Any]:
    candidates = [
        row for row in rows
        if row.get("provider") == provider and str(row.get("pack") or "").lower() == "en"
    ]
    if not candidates:
        return {"health": "UNKNOWN", "match": "NO_PROVIDER_HEALTH_ROWS"}

    scored: list[tuple[int, str, dict[str, Any]]] = []
    locator_key = "module" if provider == "keiyoushi" else "file"
    locator = str(mapping.get(locator_key) or "")
    source_id = str(mapping.get("sourceId") or "")
    source_name = str(mapping.get("sourceName") or "")
    for row in candidates:
        score = 0
        reasons: list[str] = []
        if row.get("canonicalId") == canonical_id:
            score += 1000
            reasons.append("CANONICAL_ID")
        if locator and row.get("path") == locator:
            score += 500
            reasons.append("LOCATOR")
        if source_id and str(row.get("sourceId") or "") == source_id:
            score += 400
            reasons.append("SOURCE_ID")
        if source_name and normalize(row.get("sourceId")) == normalize(source_name):
            score += 250
            reasons.append("SOURCE_NAME_TO_ID")
        if source_name and normalize(row.get("sourceName")) == normalize(source_name):
            score += 200
            reasons.append("SOURCE_NAME")
        if score:
            scored.append((score, "+".join(reasons), row))

    if not scored:
        return {"health": "UNKNOWN", "match": "NO_IDENTITY_MATCH"}
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score = scored[0][0]
    best = [item for item in scored if item[0] == best_score]
    source_keys = {str(item[2].get("sourceKey") or "") for item in best}
    if len(best) != 1 or len(source_keys) != 1:
        return {
            "health": "UNKNOWN",
            "match": "AMBIGUOUS_IDENTITY_MATCH",
            "candidateSourceKeys": sorted(source_keys),
        }
    _, match, row = best[0]
    observed_health = str(row.get("runtimeHealth") or "UNKNOWN").upper()
    if observed_health not in HEALTH:
        observed_health = "UNKNOWN"
    evidence_commit = str(row.get("activeCommit") or "")
    if not expected_commit:
        health = "UNKNOWN"
        match_state = "UNBOUND_HEALTH_COMMIT"
    elif evidence_commit != expected_commit:
        health = "UNKNOWN"
        match_state = "STALE_HEALTH_COMMIT_MISMATCH"
    else:
        health = observed_health
        match_state = match
    return {
        "health": health,
        "match": match_state,
        "identityMatch": match,
        "observedRuntimeHealth": observed_health,
        "sourceKey": row.get("sourceKey"),
        "activeCommit": row.get("activeCommit"),
        "expectedCommit": expected_commit,
        "probeHost": row.get("probeHost"),
        "probeOutcome": row.get("probeOutcome"),
        "recoveryState": row.get("recoveryState"),
        "consecutiveFailures": row.get("consecutiveFailures"),
    }


def structural_rows(b1: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    findings = b1.get("findings")
    if not isinstance(findings, dict):
        raise ValueError("B1 findings missing")
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for kind in STRUCTURAL_FINDINGS:
        values = findings.get(kind)
        if not isinstance(values, list):
            raise ValueError(f"B1 finding list missing: {kind}")
        for value in values:
            if isinstance(value, str):
                canonical_id = value
                detail: dict[str, Any] = {}
            elif isinstance(value, dict) and isinstance(value.get("canonicalId"), str):
                canonical_id = value["canonicalId"]
                detail = copy.deepcopy(value)
                detail.pop("canonicalId", None)
            else:
                raise ValueError(f"invalid B1 finding item in {kind}")
            by_id[canonical_id].append({"type": kind, "detail": detail})
    expected = b1.get("summary", {}).get("structuralAttentionCount")
    if not isinstance(expected, int):
        raise ValueError("B1 structuralAttentionCount missing")
    actual = sum(len(items) for items in by_id.values())
    if actual != expected:
        raise ValueError(f"B1 structural cohort mismatch: expected={expected} actual={actual}")
    if len(by_id) != actual:
        raise ValueError("B2 requires one structural finding per canonical source in this batch")
    return dict(by_id)


def index_en_sources(value: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    rows = value.get("sources")
    if not isinstance(rows, list):
        raise ValueError(f"{label} sources must be a list")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("language") != "en":
            continue
        canonical_id = row.get("canonicalId")
        if not isinstance(canonical_id, str) or canonical_id in indexed:
            raise ValueError(f"invalid or duplicate EN canonicalId in {label}: {canonical_id}")
        indexed[canonical_id] = row
    return indexed


def primary_state(provider_rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    present = [provider for provider in PRIMARY if provider_rows[provider]["presentInFarm"]]
    healthy = [provider for provider in present if provider_rows[provider]["health"]["health"] == "HEALTHY"]
    degraded = [provider for provider in present if provider_rows[provider]["health"]["health"] == "DEGRADED"]
    unavailable = [provider for provider in present if provider_rows[provider]["health"]["health"] in {"UNAVAILABLE", "DEPRECATED"}]
    if len(healthy) == 2:
        preference = "BOTH_PRIMARY_HEALTHY"
        aggregate = "HEALTHY"
    elif len(healthy) == 1:
        preference = f"{healthy[0].upper()}_HEALTHY_PREFERRED"
        aggregate = "HEALTHY"
    elif not present:
        preference = "NO_PRIMARY_PROVIDER"
        aggregate = "UNKNOWN"
    elif degraded:
        preference = "NO_HEALTHY_PRIMARY"
        aggregate = "DEGRADED"
    elif len(unavailable) == len(present):
        preference = "NO_HEALTHY_PRIMARY"
        aggregate = "UNAVAILABLE"
    else:
        preference = "NO_PROVEN_PRIMARY_HEALTH"
        aggregate = "UNKNOWN"
    return {
        "present": present,
        "healthy": healthy,
        "aggregateHealth": aggregate,
        "preference": preference,
    }


def same_module_source_id_only(detail: dict[str, Any]) -> bool:
    farm = parse_identity(str(detail.get("farmIdentity") or ""))
    inventory = parse_identity(str(detail.get("inventoryIdentity") or ""))
    return (
        bool(farm.get("module"))
        and farm.get("module") == inventory.get("module")
        and farm.get("sourceId") != inventory.get("sourceId")
    )


def route_decision(
    finding: dict[str, Any],
    provider_rows: dict[str, dict[str, Any]],
    primary: dict[str, Any],
) -> dict[str, str]:
    kind = finding["type"]
    detail = finding["detail"]
    affected = str(detail.get("provider") or "")

    if kind == "providerIdentityDrift":
        if affected == "keiyoushi" and same_module_source_id_only(detail):
            return {
                "decision": "DEFER_TRACK_C_REFERENCE_ID_RECONCILIATION",
                "nextPhase": "TRACK_C",
                "reason": "Keiyoushi is reference-only and the mapped module is stable; only its upstream numeric sourceId drifted.",
            }
        return {
            "decision": "B3_TARGETED_IDENTITY_INVESTIGATION",
            "nextPhase": "TRACK_B_BATCH_3",
            "reason": "Identity drift is not a reference-only numeric-ID change that can safely be deferred.",
        }

    if kind == "farmProviderNotDiscovered":
        if affected == "keiyoushi":
            if primary["healthy"]:
                return {
                    "decision": "NO_TRACK_B_REPAIR_REFERENCE_ONLY_GAP",
                    "nextPhase": "TRACK_D",
                    "reason": "A healthy primary provider is proven; the undiscovered Keiyoushi membership is reference-only and non-blocking for Track B.",
                }
            if primary["present"]:
                return {
                    "decision": "B3_VALIDATE_PRIMARY_BEFORE_IGNORING_REFERENCE_GAP",
                    "nextPhase": "TRACK_B_BATCH_3",
                    "reason": "Primary implementation exists but health is not proven; validate primary runtime before treating the Keiyoushi gap as non-blocking.",
                }
            return {
                "decision": "B3_PRIMARY_COVERAGE_DISCOVERY_REQUIRED",
                "nextPhase": "TRACK_B_BATCH_3",
                "reason": "Only a reference-provider membership is present; Track B requires UMA/Gekkoushi coverage or an explicit unsupported/unavailable decision.",
            }
        if affected in PRIMARY:
            other = [p for p in primary["healthy"] if p != affected]
            if other:
                return {
                    "decision": "B3_RECONCILE_MISSING_PRIMARY_WITH_HEALTHY_FALLBACK",
                    "nextPhase": "TRACK_B_BATCH_3",
                    "reason": "The affected primary membership is no longer discovered, but another healthy primary is proven as a safe fallback during targeted reconciliation.",
                }
            return {
                "decision": "B3_TARGETED_PRIMARY_DISCOVERY_VALIDATION",
                "nextPhase": "TRACK_B_BATCH_3",
                "reason": "A primary provider enrolled in Farm is no longer discovered and no healthy alternate primary is proven.",
            }

    if kind == "farmCanonicalMissingFromInventory":
        if primary["healthy"]:
            return {
                "decision": "B3_RECONCILE_DISCOVERY_WITH_HEALTHY_PRIMARY_LKG",
                "nextPhase": "TRACK_B_BATCH_3",
                "reason": "Farm still has a healthy primary identity while discovery lost the canonical source; preserve LKG and reconcile the discovery/runtime path.",
            }
        if primary["aggregateHealth"] == "DEGRADED":
            return {
                "decision": "B3_TARGETED_REPAIR_AND_DISCOVERY_VALIDATION",
                "nextPhase": "TRACK_B_BATCH_3",
                "reason": "The canonical source disappeared from discovery and its best primary evidence is degraded.",
            }
        if primary["aggregateHealth"] == "UNAVAILABLE":
            return {
                "decision": "B3_CONFIRM_UNAVAILABLE_OR_REPLACEMENT",
                "nextPhase": "TRACK_B_BATCH_3",
                "reason": "Discovery lost the canonical source and all known primary evidence is unavailable/deprecated; confirm replacement or unsupported status without replacing LKG prematurely.",
            }
        if primary["present"]:
            return {
                "decision": "B3_RUNTIME_AND_DISCOVERY_VALIDATION_REQUIRED",
                "nextPhase": "TRACK_B_BATCH_3",
                "reason": "Primary membership exists but current provider health is not proven for the discovery-missing canonical source.",
            }
        return {
            "decision": "B3_PRIMARY_COVERAGE_DECISION_REQUIRED",
            "nextPhase": "TRACK_B_BATCH_3",
            "reason": "The canonical source is absent from discovery and Farm has no primary UMA/Gekkoushi membership; determine primary support, permanent unavailability, or exceptional overlay need.",
        }

    raise ValueError(f"unhandled finding type: {kind}")


def build_report(
    b1: dict[str, Any],
    inventory: dict[str, Any],
    farm: dict[str, Any],
    source_health: dict[str, Any],
    *,
    inventory_commit: str = "",
    foundation_commit: str = "",
    miyorare_commit: str = "",
    control_commit: str = "",
) -> dict[str, Any]:
    if b1.get("phase") != "TRACK_B_BATCH_1_EN_AUDIT_MAPPING" or b1.get("readOnly") is not True:
        raise ValueError("B2 requires a read-only Track B Batch 1 report")
    if inventory.get("kind") != "MIYORARE_SOURCE_INVENTORY" or inventory.get("informationalOnly") is not True:
        raise ValueError("inventory must remain informational discovery data")
    if farm.get("schemaVersion") != 1:
        raise ValueError("unsupported Compatibility Farm registry schema")

    cohort = structural_rows(b1)
    inventory_by_id = index_en_sources(inventory, "inventory")
    farm_by_id = index_en_sources(farm, "farm")
    hrows = health_rows(source_health)

    output: list[dict[str, Any]] = []
    for canonical_id in sorted(cohort):
        findings = cohort[canonical_id]
        finding = findings[0]
        farm_source = farm_by_id.get(canonical_id)
        if farm_source is None:
            raise ValueError(f"{canonical_id}: structural B1 cohort source missing from Farm")
        inventory_source = inventory_by_id.get(canonical_id)
        inventory_providers = inventory_source.get("providers", {}) if isinstance(inventory_source, dict) and isinstance(inventory_source.get("providers"), dict) else {}
        farm_identities = farm_source.get("upstreamIdentities", {}) if isinstance(farm_source.get("upstreamIdentities"), dict) else {}
        farm_memberships = set(farm_source.get("providers") or []) | set(farm_identities)

        provider_rows: dict[str, dict[str, Any]] = {}
        current_versions = farm_source.get("currentVersion") if isinstance(farm_source.get("currentVersion"), dict) else {}
        last_known_good = farm_source.get("lastKnownGood") if isinstance(farm_source.get("lastKnownGood"), dict) else {}
        for provider in PROVIDERS:
            farm_mapping = farm_identities.get(provider) if isinstance(farm_identities.get(provider), dict) else {}
            inv_mapping = inventory_providers.get(provider) if isinstance(inventory_providers.get(provider), dict) else {}
            present = provider in farm_memberships
            discovered = provider in inventory_providers
            mapping = farm_mapping or inv_mapping
            expected_commit = str(current_versions.get(provider) or last_known_good.get(provider) or "") or None
            health = unique_health_match(
                hrows,
                canonical_id=canonical_id,
                provider=provider,
                mapping=mapping,
                expected_commit=expected_commit,
            ) if mapping else {"health": "UNKNOWN", "match": "NO_PROVIDER_IDENTITY"}
            provider_rows[provider] = {
                "presentInFarm": present,
                "discoveredInInventory": discovered,
                "farmIdentity": copy.deepcopy(farm_mapping) if farm_mapping else None,
                "inventoryIdentity": copy.deepcopy(inv_mapping) if inv_mapping else None,
                "identityAligned": (
                    provider_identity(provider, farm_mapping) == provider_identity(provider, inv_mapping)
                    if farm_mapping and inv_mapping else None
                ),
                "health": health,
            }

        primary = primary_state(provider_rows)
        decision = route_decision(finding, provider_rows, primary)
        baseline = farm_source.get("compatibilityBaseline") if isinstance(farm_source.get("compatibilityBaseline"), dict) else {}
        output.append({
            "canonicalId": canonical_id,
            "displayName": farm_source.get("displayName") or (inventory_source or {}).get("displayName") or canonical_id.rsplit(":", 1)[-1],
            "finding": finding,
            "inventoryPresent": inventory_source is not None,
            "farmEnrollmentState": (farm_source.get("compatibilityEnrollment") or {}).get("state") if isinstance(farm_source.get("compatibilityEnrollment"), dict) else None,
            "declaredCapabilities": list(baseline.get("capabilities") or []),
            "capabilityBaselineStatus": baseline.get("status"),
            "authType": farm_source.get("authType"),
            "adapterFamily": farm_source.get("adapterFamily"),
            "contentProfile": farm_source.get("contentProfile"),
            "providers": provider_rows,
            "primaryDecision": primary,
            "decision": decision,
            "safety": {
                "preserveCanonicalId": True,
                "preserveLastKnownGood": True,
                "mutateRetryHeld": False,
                "adoptKeiyoushiAsPrimary": False,
                "overlayApproved": False,
            },
        })

    decision_counts = Counter(row["decision"]["decision"] for row in output)
    health_counts = Counter(row["primaryDecision"]["aggregateHealth"] for row in output)
    preference_counts = Counter(row["primaryDecision"]["preference"] for row in output)
    finding_counts = Counter(row["finding"]["type"] for row in output)
    unresolved = sum(1 for row in output if row["decision"]["nextPhase"] == "TRACK_B_BATCH_3")
    deferred_track_c = sum(1 for row in output if row["decision"]["nextPhase"] == "TRACK_C")
    deferred_track_d = sum(1 for row in output if row["decision"]["nextPhase"] == "TRACK_D")

    result = {
        "phase": "TRACK_B_BATCH_2_CAPABILITY_HEALTH_DECISION",
        "status": "COMPLETE_WITH_DECISIONS",
        "readOnly": True,
        "authority": {
            "inventoryRole": "INFORMATIONAL_DISCOVERY_ONLY",
            "farmRole": "OPERATIONAL_LKG_AND_LIFECYCLE_AUTHORITY",
            "healthRole": "PROVIDER_HEALTH_EVIDENCE_ONLY_WHEN_IDENTITY_MATCH_IS_UNIQUE",
            "primaryProviders": list(PRIMARY),
            "keiyoushiRole": "REFERENCE_RECOVERY_COMPARISON_ONLY",
            "overlayRole": "EXCEPTION_ONLY_NOT_APPROVED_BY_B2",
        },
        "provenance": {
            "controlCommit": control_commit,
            "inventoryCommit": inventory_commit,
            "foundationCommit": foundation_commit,
            "miyorareCommit": miyorare_commit,
            "b1Provenance": copy.deepcopy(b1.get("provenance", {})),
        },
        "summary": {
            "decisionRows": len(output),
            "b1StructuralAttentionCount": b1["summary"]["structuralAttentionCount"],
            "findings": dict(sorted(finding_counts.items())),
            "primaryHealth": dict(sorted(health_counts.items())),
            "primaryPreference": dict(sorted(preference_counts.items())),
            "decisions": dict(sorted(decision_counts.items())),
            "batch3Rows": unresolved,
            "deferredTrackCRows": deferred_track_c,
            "deferredTrackDRows": deferred_track_d,
            "informationalB1ObservationsExcludedFrom38": {
                "inventoryCanonicalNotEnrolledInFarm": len(b1.get("findings", {}).get("inventoryCanonicalNotEnrolledInFarm", [])),
                "discoveredProviderNotEnrolled": len(b1.get("findings", {}).get("discoveredProviderNotEnrolled", [])),
                "referenceOnlyKeiyoushi": len(b1.get("findings", {}).get("referenceOnlyKeiyoushi", [])),
            },
        },
        "decisions": output,
    }
    if result["summary"]["decisionRows"] != result["summary"]["b1StructuralAttentionCount"]:
        raise ValueError("B2 decision matrix must cover the complete B1 structural cohort")
    return result


def markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Track B Batch 2 — Capability & Health Decision",
        "",
        f"Status: **{report['status']}**",
        "",
        "This is a read-only decision matrix. Presence is not treated as health; provider health is used only when an exact/unique identity match exists.",
        "",
        "## Summary",
        "",
        f"- Decision rows: **{s['decisionRows']}**",
        f"- Routed to Batch 3: **{s['batch3Rows']}**",
        f"- Deferred to Track C ID reconciliation: **{s['deferredTrackCRows']}**",
        f"- Deferred to Track D convergence: **{s['deferredTrackDRows']}**",
        "",
        "## Matrix",
        "",
        "| Canonical source | B1 finding | Primary health | Primary preference | Decision | Next |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["decisions"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row["canonicalId"],
                row["finding"]["type"],
                row["primaryDecision"]["aggregateHealth"],
                row["primaryDecision"]["preference"],
                row["decision"]["decision"],
                row["decision"]["nextPhase"],
            )
        )
    lines += [
        "",
        "## Safety boundary",
        "",
        "- Canonical IDs are preserved.",
        "- Last-Known-Good is not mutated.",
        "- Retry/Held state is not mass-mutated.",
        "- Keiyoushi is never promoted to a primary shard by this phase.",
        "- Miyorare overlay is not approved by Batch 2; it remains an exception candidate for later evidence-based handling.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--b1-report", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--farm-registry", type=Path, required=True)
    parser.add_argument("--source-health", type=Path, required=True)
    parser.add_argument("--inventory-commit", default="")
    parser.add_argument("--foundation-commit", default="")
    parser.add_argument("--miyorare-commit", default="")
    parser.add_argument("--control-commit", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(
        load_json(args.b1_report),
        load_json(args.inventory),
        load_json(args.farm_registry),
        load_json(args.source_health),
        inventory_commit=args.inventory_commit,
        foundation_commit=args.foundation_commit,
        miyorare_commit=args.miyorare_commit,
        control_commit=args.control_commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
