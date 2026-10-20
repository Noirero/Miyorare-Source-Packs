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
LANGUAGE = "id"
HEALTH = {"HEALTHY", "DEGRADED", "HELD", "UNAVAILABLE", "DEPRECATED", "UNKNOWN"}
C1_FINDING_TYPES = (
    "farmCanonicalMissingFromInventory",
    "providerIdentityDrift",
    "inventoryCanonicalNotEnrolledInFarm",
    "discoveredProviderNotEnrolled",
    "inventoryUmaNotCuratedByConsumer",
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


def same_module_source_id_only(detail: dict[str, Any]) -> bool:
    farm = parse_identity(str(detail.get("farmIdentity") or ""))
    inventory = parse_identity(str(detail.get("inventoryIdentity") or ""))
    return (
        bool(farm.get("module"))
        and farm.get("module") == inventory.get("module")
        and bool(farm.get("sourceId"))
        and bool(inventory.get("sourceId"))
        and farm.get("sourceId") != inventory.get("sourceId")
    )


def index_sources(value: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    rows = value.get("sources")
    if not isinstance(rows, list):
        raise ValueError(f"{label} sources must be a list")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("language") != LANGUAGE:
            continue
        canonical_id = row.get("canonicalId")
        if not isinstance(canonical_id, str) or canonical_id in indexed:
            raise ValueError(f"invalid or duplicate ID canonicalId in {label}: {canonical_id}")
        indexed[canonical_id] = row
    return indexed


def health_rows(source_health: dict[str, Any]) -> list[dict[str, Any]]:
    raw = source_health.get("sources", {})
    if isinstance(raw, dict):
        return [dict(value, sourceKey=value.get("sourceKey") or key) for key, value in raw.items() if isinstance(value, dict)]
    if isinstance(raw, list):
        return [dict(value) for value in raw if isinstance(value, dict)]
    raise ValueError("source health sources must be a mapping or list")


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
        if row.get("provider") == provider and str(row.get("pack") or "").lower() == LANGUAGE
    ]
    if not candidates:
        return {"health": "UNKNOWN", "match": "NO_PROVIDER_HEALTH_ROWS"}

    locator_key = "module" if provider == "keiyoushi" else "file"
    locator = str(mapping.get(locator_key) or "")
    source_id = str(mapping.get("sourceId") or "")
    source_name = str(mapping.get("sourceName") or "")
    scored: list[tuple[int, str, dict[str, Any]]] = []
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
    _, identity_match, row = best[0]
    observed = str(row.get("runtimeHealth") or "UNKNOWN").upper()
    if observed not in HEALTH:
        observed = "UNKNOWN"
    evidence_commit = str(row.get("activeCommit") or "")
    if not expected_commit:
        health = "UNKNOWN"
        match = "UNBOUND_HEALTH_COMMIT"
    elif evidence_commit != expected_commit:
        health = "UNKNOWN"
        match = "STALE_HEALTH_COMMIT_MISMATCH"
    else:
        health = observed
        match = identity_match
    return {
        "health": health,
        "match": match,
        "identityMatch": identity_match,
        "observedRuntimeHealth": observed,
        "sourceKey": row.get("sourceKey"),
        "activeCommit": row.get("activeCommit"),
        "expectedCommit": expected_commit,
        "probeHost": row.get("probeHost"),
        "probeOutcome": row.get("probeOutcome"),
        "recoveryState": row.get("recoveryState"),
        "consecutiveFailures": row.get("consecutiveFailures"),
    }


def curated_uma_paths(c1: dict[str, Any]) -> set[str]:
    current = c1.get("currentConsumer")
    if not isinstance(current, dict):
        raise ValueError("C1 currentConsumer missing")
    entries = current.get("umaCuratedEntries")
    if not isinstance(entries, list) or any(not isinstance(item, str) for item in entries):
        raise ValueError("C1 UMA curated entries missing")
    return {f"src/main/kotlin/tsuki/site/id/{item.lstrip('/')}" for item in entries}


def provider_role(provider: str, c1: dict[str, Any]) -> str:
    current = c1["currentConsumer"]
    if provider == "gekkoushi":
        return "CURRENT_CONSUMER_INCLUDE_ALL" if current.get("gekkoushiMode") == "INCLUDE_ALL_FROM" else "NOT_CURRENTLY_INCLUDE_ALL"
    if provider == "uma":
        return "CURRENT_CONSUMER_CURATED"
    return "REFERENCE_NOT_DIRECTLY_PACKAGED"


def consumer_coverage(provider: str, mapping: dict[str, Any], c1: dict[str, Any], curated_paths: set[str]) -> bool:
    if not mapping:
        return False
    if provider == "gekkoushi":
        return c1["currentConsumer"].get("gekkoushiMode") == "INCLUDE_ALL_FROM"
    if provider == "uma":
        return str(mapping.get("file") or "") in curated_paths
    return False


def resolve_uma_path(inventory_by_id: dict[str, dict[str, Any]], path: str) -> str:
    matches = []
    for canonical_id, source in inventory_by_id.items():
        providers = source.get("providers") if isinstance(source.get("providers"), dict) else {}
        uma = providers.get("uma") if isinstance(providers.get("uma"), dict) else {}
        if uma.get("file") == path:
            matches.append(canonical_id)
    if len(matches) != 1:
        raise ValueError(f"UMA path must resolve to exactly one ID canonical source: {path} -> {matches}")
    return matches[0]


def finding_rows(c1: dict[str, Any], inventory_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    findings = c1.get("findings")
    if not isinstance(findings, dict):
        raise ValueError("C1 findings missing")
    rows: list[dict[str, Any]] = []
    for kind in C1_FINDING_TYPES:
        values = findings.get(kind)
        if not isinstance(values, list):
            raise ValueError(f"C1 finding list missing: {kind}")
        for value in values:
            if kind == "inventoryUmaNotCuratedByConsumer":
                if not isinstance(value, str):
                    raise ValueError("invalid UMA not-curated finding")
                rows.append({
                    "type": kind,
                    "canonicalId": resolve_uma_path(inventory_by_id, value),
                    "detail": {"provider": "uma", "file": value},
                })
            elif isinstance(value, str):
                rows.append({"type": kind, "canonicalId": value, "detail": {}})
            elif isinstance(value, dict) and isinstance(value.get("canonicalId"), str):
                detail = copy.deepcopy(value)
                canonical_id = detail.pop("canonicalId")
                rows.append({"type": kind, "canonicalId": canonical_id, "detail": detail})
            else:
                raise ValueError(f"invalid C1 finding item in {kind}")
    structural_expected = c1.get("summary", {}).get("structuralAttentionCount")
    structural_actual = sum(1 for row in rows if row["type"] in {"farmCanonicalMissingFromInventory", "providerIdentityDrift"})
    if not isinstance(structural_expected, int) or structural_actual != structural_expected:
        raise ValueError(f"C1 structural cohort mismatch: expected={structural_expected} actual={structural_actual}")
    return rows


def source_assessment(
    canonical_id: str,
    *,
    inventory_by_id: dict[str, dict[str, Any]],
    farm_by_id: dict[str, dict[str, Any]],
    hrows: list[dict[str, Any]],
    c1: dict[str, Any],
    curated_paths: set[str],
) -> dict[str, Any]:
    inventory_source = inventory_by_id.get(canonical_id)
    farm_source = farm_by_id.get(canonical_id)
    inventory_providers = inventory_source.get("providers", {}) if isinstance(inventory_source, dict) and isinstance(inventory_source.get("providers"), dict) else {}
    farm_identities = farm_source.get("upstreamIdentities", {}) if isinstance(farm_source, dict) and isinstance(farm_source.get("upstreamIdentities"), dict) else {}
    farm_memberships = set(farm_source.get("providers") or []) | set(farm_identities) if isinstance(farm_source, dict) else set()
    current_versions = farm_source.get("currentVersion", {}) if isinstance(farm_source, dict) and isinstance(farm_source.get("currentVersion"), dict) else {}
    last_known_good = farm_source.get("lastKnownGood", {}) if isinstance(farm_source, dict) and isinstance(farm_source.get("lastKnownGood"), dict) else {}

    provider_rows: dict[str, Any] = {}
    coverage: list[str] = []
    trusted_health: list[str] = []
    for provider in PROVIDERS:
        inv_mapping = inventory_providers.get(provider) if isinstance(inventory_providers.get(provider), dict) else {}
        farm_mapping = farm_identities.get(provider) if isinstance(farm_identities.get(provider), dict) else {}
        enrolled = provider in farm_memberships
        discovered = bool(inv_mapping)
        mapping_for_health = farm_mapping if enrolled else {}
        expected_commit = str(current_versions.get(provider) or last_known_good.get(provider) or "") or None
        health = (
            unique_health_match(hrows, canonical_id=canonical_id, provider=provider, mapping=mapping_for_health, expected_commit=expected_commit)
            if mapping_for_health else {"health": "UNKNOWN", "match": "NOT_ENROLLED_NO_AUTHORITATIVE_IDENTITY"}
        )
        coverage_mapping = inv_mapping or farm_mapping
        covered = consumer_coverage(provider, coverage_mapping, c1, curated_paths)
        if covered:
            coverage.append(provider)
            if health.get("health") != "UNKNOWN":
                trusted_health.append(str(health["health"]))
        provider_rows[provider] = {
            "consumerRole": provider_role(provider, c1),
            "presentInFarm": enrolled,
            "discoveredInInventory": discovered,
            "currentConsumerCoverage": covered,
            "farmIdentity": copy.deepcopy(farm_mapping) if farm_mapping else None,
            "inventoryIdentity": copy.deepcopy(inv_mapping) if inv_mapping else None,
            "identityAligned": provider_identity(provider, farm_mapping) == provider_identity(provider, inv_mapping) if farm_mapping and inv_mapping else None,
            "health": health,
        }

    if "HEALTHY" in trusted_health:
        aggregate = "HEALTHY"
    elif "DEGRADED" in trusted_health:
        aggregate = "DEGRADED"
    elif coverage and trusted_health and all(value in {"UNAVAILABLE", "DEPRECATED"} for value in trusted_health):
        aggregate = "UNAVAILABLE"
    elif "HELD" in trusted_health:
        aggregate = "HELD"
    else:
        aggregate = "UNKNOWN"

    baseline = farm_source.get("compatibilityBaseline") if isinstance(farm_source, dict) and isinstance(farm_source.get("compatibilityBaseline"), dict) else {}
    enrollment = farm_source.get("compatibilityEnrollment") if isinstance(farm_source, dict) and isinstance(farm_source.get("compatibilityEnrollment"), dict) else {}
    return {
        "canonicalId": canonical_id,
        "displayName": (farm_source or inventory_source or {}).get("displayName") or canonical_id.rsplit(":", 1)[-1],
        "inventoryPresent": inventory_source is not None,
        "farmPresent": farm_source is not None,
        "farmEnrollmentState": enrollment.get("state"),
        "declaredCapabilities": list(baseline.get("capabilities") or []),
        "capabilityBaselineStatus": baseline.get("status"),
        "authType": (farm_source or {}).get("authType"),
        "adapterFamily": (farm_source or {}).get("adapterFamily"),
        "contentProfile": (farm_source or {}).get("contentProfile"),
        "currentConsumerCoverageProviders": coverage,
        "consumerCoverageHealth": aggregate,
        "providers": provider_rows,
    }


def route_decision(finding: dict[str, Any], assessment: dict[str, Any]) -> dict[str, str]:
    kind = finding["type"]
    detail = finding["detail"]
    provider = str(detail.get("provider") or "")
    coverage = assessment["currentConsumerCoverageProviders"]
    health = assessment["consumerCoverageHealth"]
    providers = assessment["providers"]

    if kind == "providerIdentityDrift":
        if provider == "keiyoushi" and same_module_source_id_only(detail):
            return {
                "decision": "C3_VERIFY_REFERENCE_IDENTITY_MIGRATION",
                "nextPhase": "TRACK_C_BATCH_3",
                "reason": "The Keiyoushi module path is stable while only sourceId changed; preserve the canonical ID and verify migration/history/runtime before changing Farm authority.",
            }
        return {
            "decision": "C3_TARGETED_IDENTITY_INVESTIGATION",
            "nextPhase": "TRACK_C_BATCH_3",
            "reason": "Identity drift is not proven to be a sourceId-only migration and requires targeted validation before authority mutation.",
        }

    if kind == "farmCanonicalMissingFromInventory":
        if health == "HEALTHY":
            decision = "C3_RECONCILE_DISCOVERY_WITH_HEALTHY_LKG"
            reason = "Farm retains healthy current/LKG evidence while candidate discovery lost the canonical source; preserve LKG and reconcile discovery/runtime."
        elif health == "DEGRADED":
            decision = "C3_REPAIR_OR_DISCOVERY_RECONCILIATION"
            reason = "The source disappeared from discovery and current consumed health is degraded; targeted runtime/discovery repair is required."
        elif health == "UNAVAILABLE":
            decision = "C3_CONFIRM_RETIREMENT_OR_REPLACEMENT"
            reason = "The source disappeared from discovery and current consumed evidence is unavailable/deprecated; confirm retirement or replacement without dropping LKG prematurely."
        else:
            decision = "C3_VALIDATE_LKG_AND_DISCOVERY_GAP"
            reason = "The source disappeared from discovery and current runtime health is not sufficiently proven; validate LKG and discovery before disposition."
        return {"decision": decision, "nextPhase": "TRACK_C_BATCH_3", "reason": reason}

    if kind == "inventoryCanonicalNotEnrolledInFarm":
        if coverage:
            return {
                "decision": "C3_RECONCILE_CONSUMED_SOURCE_FARM_ENROLLMENT",
                "nextPhase": "TRACK_C_BATCH_3",
                "reason": "The candidate is already reachable through current consumer packaging but has no Farm authority row; validate and reconcile enrollment before lifecycle decisions.",
            }
        return {
            "decision": "C3_VALIDATE_UNENROLLED_CANDIDATE_BEFORE_ADOPTION",
            "nextPhase": "TRACK_C_BATCH_3",
            "reason": "The candidate is neither Farm-enrolled nor currently packaged; validate runtime/capability before any enrollment or adoption decision.",
        }

    if kind == "discoveredProviderNotEnrolled":
        candidate = providers.get(provider, {})
        if candidate.get("currentConsumerCoverage"):
            return {
                "decision": "C3_RECONCILE_CONSUMED_PROVIDER_ENROLLMENT",
                "nextPhase": "TRACK_C_BATCH_3",
                "reason": "This provider identity is consumed today but is not represented in Farm authority; targeted enrollment/runtime validation is required.",
            }
        if provider == "keiyoushi":
            if coverage:
                return {
                    "decision": "NO_C3_REFERENCE_ONLY_PROVIDER_DISCOVERY",
                    "nextPhase": "TRACK_C_BATCH_4",
                    "reason": "Keiyoushi is not directly packaged and current consumer coverage already exists; retain it as reference evidence and automate drift tracking rather than adopting it.",
                }
            return {
                "decision": "C3_REFERENCE_ONLY_RECOVERY_EVIDENCE_REQUIRED",
                "nextPhase": "TRACK_C_BATCH_3",
                "reason": "No current consumer coverage is present; use the Keiyoushi discovery only as recovery/comparison evidence, not as an automatic primary adoption.",
            }
        if coverage:
            return {
                "decision": "NO_C3_REDUNDANT_PROVIDER_DISCOVERY",
                "nextPhase": "TRACK_C_BATCH_4",
                "reason": "Current consumer coverage already exists through another packaged provider; the extra discovered identity is an adoption/drift observation, not a Batch 3 repair requirement.",
            }
        return {
            "decision": "C3_VALIDATE_PROVIDER_CANDIDATE_FOR_COVERAGE_GAP",
            "nextPhase": "TRACK_C_BATCH_3",
            "reason": "The discovered provider is not enrolled and the source has no current consumer coverage; validate capability/runtime before enrollment or adoption.",
        }

    if kind == "inventoryUmaNotCuratedByConsumer":
        uma = providers["uma"]
        if "gekkoushi" in coverage:
            return {
                "decision": "NO_C3_UMA_NOT_CURATED_REDUNDANT_COVERAGE",
                "nextPhase": "TRACK_C_BATCH_4",
                "reason": "The source is already packaged through Gekkoushi include-all; UMA non-curation alone is not a repair signal and must not trigger automatic adoption.",
            }
        if uma.get("presentInFarm") is False:
            return {
                "decision": "C3_LINKED_UMA_ENROLLMENT_VALIDATION",
                "nextPhase": "TRACK_C_BATCH_3",
                "reason": "UMA is not curated and its identity is not Farm-enrolled; resolve provider enrollment/runtime evidence before considering consumer adoption.",
            }
        uma_health = str(uma.get("health", {}).get("health") or "UNKNOWN")
        if uma_health == "HEALTHY":
            return {
                "decision": "C4_ADOPTION_CANDIDATE_NO_AUTO_ADOPTION",
                "nextPhase": "TRACK_C_BATCH_4",
                "reason": "Farm has current healthy UMA evidence but the consumer intentionally does not curate it; treat this as a later adoption decision, not an automatic Batch 2 change.",
            }
        return {
            "decision": "C3_VALIDATE_UNCURATED_UMA_BEFORE_ADOPTION",
            "nextPhase": "TRACK_C_BATCH_3",
            "reason": "UMA is not currently curated and current health is not proven healthy; targeted validation is required before any adoption decision.",
        }

    raise ValueError(f"unhandled finding type: {kind}")


def validate_c1(c1: dict[str, Any], *, inventory_commit: str, foundation_commit: str, miyorare_commit: str) -> None:
    if c1.get("phase") != "TRACK_C_BATCH_1_ID_AUDIT_MAPPING" or c1.get("readOnly") is not True or c1.get("language") != LANGUAGE:
        raise ValueError("C2 requires the exact read-only Track C Batch 1 ID report")
    if c1.get("status") not in {"COMPLETE", "COMPLETE_WITH_FINDINGS"}:
        raise ValueError("C1 report did not complete")
    provenance = c1.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("C1 provenance missing")
    expected = {
        "inventoryCommit": inventory_commit,
        "foundationCommit": foundation_commit,
        "miyorareCommit": miyorare_commit,
    }
    for key, value in expected.items():
        if value and provenance.get(key) != value:
            raise ValueError(f"C1 provenance mismatch for {key}: {provenance.get(key)} != {value}")


def build_report(
    c1: dict[str, Any],
    inventory: dict[str, Any],
    farm: dict[str, Any],
    source_health: dict[str, Any],
    *,
    inventory_commit: str = "",
    foundation_commit: str = "",
    miyorare_commit: str = "",
    control_commit: str = "",
    c1_run_id: str = "",
    c1_artifact_id: str = "",
    c1_artifact_digest: str = "",
) -> dict[str, Any]:
    validate_c1(c1, inventory_commit=inventory_commit, foundation_commit=foundation_commit, miyorare_commit=miyorare_commit)
    if inventory.get("kind") != "MIYORARE_SOURCE_INVENTORY" or inventory.get("informationalOnly") is not True:
        raise ValueError("inventory must remain informational discovery data")
    if farm.get("schemaVersion") != 1:
        raise ValueError("unsupported Compatibility Farm registry schema")

    inventory_by_id = index_sources(inventory, "inventory")
    farm_by_id = index_sources(farm, "farm")
    hrows = health_rows(source_health)
    curated_paths = curated_uma_paths(c1)
    findings = finding_rows(c1, inventory_by_id)

    assessments: dict[str, dict[str, Any]] = {}
    decisions: list[dict[str, Any]] = []
    for finding in findings:
        canonical_id = finding["canonicalId"]
        if canonical_id not in assessments:
            assessments[canonical_id] = source_assessment(
                canonical_id,
                inventory_by_id=inventory_by_id,
                farm_by_id=farm_by_id,
                hrows=hrows,
                c1=c1,
                curated_paths=curated_paths,
            )
        assessment = assessments[canonical_id]
        decision = route_decision(finding, assessment)
        decisions.append({
            "canonicalId": canonical_id,
            "finding": copy.deepcopy(finding),
            "consumerCoverageProviders": list(assessment["currentConsumerCoverageProviders"]),
            "consumerCoverageHealth": assessment["consumerCoverageHealth"],
            "decision": decision,
            "safety": {
                "preserveCanonicalId": True,
                "preserveLastKnownGood": True,
                "mutateAuthority": False,
                "mutateRetryHeld": False,
                "autoAdoptProvider": False,
            },
        })

    finding_counts = Counter(row["finding"]["type"] for row in decisions)
    decision_counts = Counter(row["decision"]["decision"] for row in decisions)
    next_counts = Counter(row["decision"]["nextPhase"] for row in decisions)

    c3_grouped: dict[str, set[str]] = defaultdict(set)
    for row in decisions:
        if row["decision"]["nextPhase"] == "TRACK_C_BATCH_3":
            c3_grouped[row["canonicalId"]].add(row["decision"]["decision"])
    c3_candidates = [
        {"canonicalId": canonical_id, "reasons": sorted(reasons)}
        for canonical_id, reasons in sorted(c3_grouped.items())
    ]

    result = {
        "phase": "TRACK_C_BATCH_2_ID_CAPABILITY_HEALTH_DECISION",
        "status": "COMPLETE_WITH_DECISIONS",
        "readOnly": True,
        "language": LANGUAGE,
        "authority": {
            "inventoryRole": "INFORMATIONAL_DISCOVERY_ONLY",
            "farmRole": "OPERATIONAL_LKG_AND_LIFECYCLE_AUTHORITY",
            "healthRole": "TRUST_ONLY_UNIQUE_IDENTITY_MATCH_ON_AUTHORITATIVE_FARM_VERSION",
            "consumerRole": "AMAIN2_PACKAGING_CONFIGURATION",
            "providerRoles": {
                "gekkoushi": "CURRENT_CONSUMER_INCLUDE_ALL",
                "uma": "CURRENT_CONSUMER_CURATED",
                "keiyoushi": "REFERENCE_NOT_DIRECTLY_PACKAGED",
            },
            "providerSelection": "NO_GLOBAL_PRIMARY_PROVIDER_ASSUMPTION",
        },
        "provenance": {
            "controlCommit": control_commit,
            "inventoryCommit": inventory_commit,
            "foundationCommit": foundation_commit,
            "miyorareCommit": miyorare_commit,
            "c1": {
                "runId": c1_run_id,
                "artifactId": c1_artifact_id,
                "artifactDigest": c1_artifact_digest,
                "reportProvenance": copy.deepcopy(c1.get("provenance", {})),
            },
        },
        "summary": {
            "findingRows": len(decisions),
            "structuralAttentionCount": c1["summary"]["structuralAttentionCount"],
            "findings": dict(sorted(finding_counts.items())),
            "decisions": dict(sorted(decision_counts.items())),
            "nextPhases": dict(sorted(next_counts.items())),
            "c3FindingRows": next_counts.get("TRACK_C_BATCH_3", 0),
            "c3CanonicalSources": len(c3_candidates),
            "c4FindingRows": next_counts.get("TRACK_C_BATCH_4", 0),
        },
        "sourceAssessments": [assessments[key] for key in sorted(assessments)],
        "findingDecisions": decisions,
        "c3Candidates": c3_candidates,
        "safetyBoundary": {
            "canonicalIdsPreserved": True,
            "lastKnownGoodPreserved": True,
            "authorityMutated": False,
            "retryHeldMassMutation": False,
            "providerAutoAdoption": False,
        },
    }
    expected_rows = sum(len(c1["findings"].get(kind, [])) for kind in C1_FINDING_TYPES)
    if result["summary"]["findingRows"] != expected_rows:
        raise ValueError("C2 decision matrix must cover every C1 finding in scope")
    return result


def markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Track C Batch 2 — ID Capability & Health Decision",
        "",
        f"Status: **{report['status']}**",
        "",
        "This phase is read-only. It separates current Amain2 packaging roles from Farm runtime-health authority and does not reuse Track B provider-role assumptions.",
        "",
        "## Summary",
        "",
        f"- C1 finding rows covered: **{s['findingRows']}**",
        f"- Structural-attention rows: **{s['structuralAttentionCount']}**",
        f"- Routed to Track C Batch 3: **{s['c3FindingRows']}** finding rows across **{s['c3CanonicalSources']}** canonical sources",
        f"- Routed directly to Track C Batch 4: **{s['c4FindingRows']}** finding rows",
        "",
        "## Provider role boundary",
        "",
        "- Gekkoushi: current Amain2 include-all packaging role.",
        "- UMA: current Amain2 curated-file packaging role.",
        "- Keiyoushi: reference/not-directly-packaged role.",
        "- No provider is promoted to a global primary role by Batch 2.",
        "",
        "## Finding decisions",
        "",
        "| Canonical source | C1 finding | Coverage | Health | Decision | Next |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["findingDecisions"]:
        coverage = ",".join(row["consumerCoverageProviders"]) or "none"
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row["canonicalId"], row["finding"]["type"], coverage,
                row["consumerCoverageHealth"], row["decision"]["decision"], row["decision"]["nextPhase"],
            )
        )
    lines += [
        "",
        "## Batch 3 canonical candidates",
        "",
    ]
    for row in report["c3Candidates"]:
        lines.append(f"- `{row['canonicalId']}` — {', '.join(row['reasons'])}")
    lines += [
        "",
        "## Safety boundary",
        "",
        "- Canonical IDs remain stable, including sourceId-only migration candidates.",
        "- Compatibility Farm Last-Known-Good is not replaced or mutated.",
        "- Retry/Held state is not mass-mutated.",
        "- Keiyoushi is not auto-adopted into the consumer.",
        "- UMA discoveries that are not currently curated are not auto-adopted.",
        "- No authority state is changed by Batch 2.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--c1-report", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--farm-registry", type=Path, required=True)
    parser.add_argument("--source-health", type=Path, required=True)
    parser.add_argument("--inventory-commit", default="")
    parser.add_argument("--foundation-commit", default="")
    parser.add_argument("--miyorare-commit", default="")
    parser.add_argument("--control-commit", default="")
    parser.add_argument("--c1-run-id", default="")
    parser.add_argument("--c1-artifact-id", default="")
    parser.add_argument("--c1-artifact-digest", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(
        load_json(args.c1_report), load_json(args.inventory), load_json(args.farm_registry), load_json(args.source_health),
        inventory_commit=args.inventory_commit, foundation_commit=args.foundation_commit, miyorare_commit=args.miyorare_commit,
        control_commit=args.control_commit, c1_run_id=args.c1_run_id, c1_artifact_id=args.c1_artifact_id,
        c1_artifact_digest=args.c1_artifact_digest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
