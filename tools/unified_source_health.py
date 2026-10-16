#!/usr/bin/env python3
"""Build and validate a deterministic, fail-closed per-source health projection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

HEALTH = {"HEALTHY", "DEGRADED", "HELD", "UNAVAILABLE", "DEPRECATED", "UNKNOWN"}
LIFECYCLE = {"candidate", "validated", "active", "degraded", "held", "unavailable", "deprecated", "migrated"}
PROVIDERS = {"keiyoushi", "uma", "gekkoushi"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def canonical_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if registry.get("schemaVersion") != 2 or registry.get("kind") != "MIYORARE_CANONICAL_SOURCE_REGISTRY":
        raise ValueError("P2-A requires Canonical Source Registry V2 authority")
    indexed: dict[str, dict[str, Any]] = {}
    for source in registry.get("sources", []):
        canonical = source.get("canonicalId")
        if not isinstance(canonical, str) or canonical in indexed:
            raise ValueError(f"invalid or duplicate canonical authority: {canonical}")
        indexed[canonical] = source
    return indexed


def lifecycle_for(source: dict[str, Any], authority: dict[str, Any]) -> str:
    authoritative = authority.get("lifecycle", {}).get("state")
    if authoritative in LIFECYCLE:
        return authoritative
    raise ValueError(f"{source.get('canonicalId')}: canonical lifecycle authority missing")


def upstream_source_index(status: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for provider, pdata in status.get("providers", {}).items():
        if not isinstance(pdata, dict):
            continue
        for item in pdata.get("sourceStatus", []) or []:
            if not isinstance(item, dict):
                continue
            canonical = item.get("canonicalId")
            if not isinstance(canonical, str):
                continue
            enriched = dict(item)
            enriched["provider"] = provider
            if canonical in indexed:
                duplicates.append(canonical)
            else:
                indexed[canonical] = enriched
    return indexed, sorted(set(duplicates))


def health_for(source: dict[str, Any], lifecycle: str, upstream_source: dict[str, Any] | None) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if lifecycle == "deprecated":
        return "DEPRECATED", ["LIFECYCLE_DEPRECATED"]
    if lifecycle == "held" and not source.get("packs"):
        return "HELD", ["PACK_MEMBERSHIP_UNDECLARED"]
    if upstream_source:
        state = str(upstream_source.get("state", "")).lower()
        if state in {"review-required", "held", "hold"}:
            return "HELD", ["EXPLICIT_UPSTREAM_SOURCE_HOLD"]
    raw = str(source.get("runtimeHealth", "UNKNOWN")).upper()
    if raw in HEALTH - {"UNKNOWN"}:
        reasons.append(f"FARM_RUNTIME_{raw}")
        return raw, reasons
    approval = str(source.get("approvalState", "")).upper()
    if approval in {"HELD", "REVIEW_REQUIRED"}:
        return "HELD", ["FARM_APPROVAL_HOLD"]
    baseline = str(source.get("compatibilityBaseline", {}).get("status", "UNKNOWN")).upper()
    if baseline not in {"VALIDATED", "PASS", "PASSED"}:
        reasons.append(f"BASELINE_{baseline or 'UNKNOWN'}")
    if source.get("publishEligible") is not True:
        reasons.append("PUBLISH_NOT_ELIGIBLE")
    reasons.append("NO_PROVEN_SOURCE_HEALTH")
    return "UNKNOWN", reasons


def build(farm: dict[str, Any], upstream: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    if farm.get("schemaVersion") != 1:
        raise ValueError("P2-A currently projects Compatibility Farm schemaVersion 1 only")
    authorities = canonical_index(registry)
    source_index, duplicate_status = upstream_source_index(upstream)
    farm_ids: set[str] = set()
    output: list[dict[str, Any]] = []
    provider_status = upstream.get("providers", {}) if isinstance(upstream.get("providers", {}), dict) else {}
    for old in farm.get("sources", []):
        canonical = old.get("canonicalId")
        if not isinstance(canonical, str) or not canonical.startswith("miyorare:") or canonical in farm_ids:
            raise ValueError(f"invalid or duplicate canonicalId: {canonical}")
        farm_ids.add(canonical)
        authority = authorities.get(canonical)
        if authority is None:
            raise ValueError(f"{canonical}: missing Canonical Source Registry V2 authority")
        packs = authority.get("packs")
        origin = authority.get("origin")
        if not isinstance(packs, list) or not isinstance(origin, dict):
            raise ValueError(f"{canonical}: canonical pack/origin authority missing")
        language = str(old.get("language", "unknown")).lower()
        lifecycle = lifecycle_for(old, authority)
        explicit = source_index.get(canonical)
        health, reasons = health_for(dict(old, packs=packs), lifecycle, explicit)
        providers = []
        for provider in sorted(p for p in old.get("providers", []) if p in PROVIDERS):
            context = provider_status.get(provider, {})
            providers.append({
                "name": provider,
                "status": context.get("state") if isinstance(context, dict) else None,
                "candidate": context.get("candidate") if isinstance(context, dict) else None,
                "lastKnownGood": (old.get("lastKnownGood", {}) or {}).get(provider),
                "currentVersion": (old.get("currentVersion", {}) or {}).get(provider),
            })
        baseline = old.get("compatibilityBaseline", {}) if isinstance(old.get("compatibilityBaseline", {}), dict) else {}
        enrollment = old.get("enrollmentEvidence", {}) if isinstance(old.get("enrollmentEvidence", {}), dict) else {}
        evidence: list[dict[str, Any]] = [
            {"kind": "canonical-authority", "packs": packs, "originAuthority": origin.get("authority")},
            {"kind": "farm-runtime", "runtimeHealth": str(old.get("runtimeHealth", "UNKNOWN")).upper()},
            {"kind": "farm-baseline", "status": baseline.get("status")},
            {"kind": "lkg", "providers": old.get("lastKnownGood", {}) or {}},
        ]
        if enrollment:
            evidence.append({"kind": "farm-enrollment", "workflowRunId": enrollment.get("workflowRunId"), "inventoryCommit": enrollment.get("inventoryCommit")})
        if explicit:
            evidence.append({"kind": "upstream-source-status", "provider": explicit.get("provider"), "state": explicit.get("state"), "action": explicit.get("action")})
        for provider in providers:
            if provider["status"] is not None:
                evidence.append({"kind": "upstream-provider-status", "provider": provider["name"], "status": provider["status"]})
        output.append({
            "canonicalId": canonical,
            "displayName": old.get("displayName") or canonical.rsplit(":", 1)[-1],
            "language": language,
            "packs": packs,
            "health": health,
            "lifecycle": lifecycle,
            "reasonCodes": reasons,
            "providers": providers,
            "origin": origin,
            "lastKnownGood": old.get("lastKnownGood", {}) or {},
            "lastValidation": {"state": baseline.get("status") or "UNKNOWN", "workflowRunId": enrollment.get("workflowRunId"), "checkedAt": None},
            "lastCheck": {"workflowRunId": upstream.get("workflowRunId"), "checkedAt": None},
            "evidence": evidence,
        })
    if set(authorities) != farm_ids:
        extra = sorted(set(authorities) - farm_ids)
        missing = sorted(farm_ids - set(authorities))
        raise ValueError(f"canonical authority identity set differs from Farm: extra={extra[:5]} missing={missing[:5]}")
    unmatched = sorted(set(source_index) - farm_ids)
    result = {
        "schemaVersion": 1,
        "kind": "MIYORARE_UNIFIED_SOURCE_HEALTH",
        "sourceCount": len(output),
        "sources": sorted(output, key=lambda item: item["canonicalId"]),
        "observability": {"unmatchedUpstreamSourceStatus": unmatched, "duplicateUpstreamSourceStatus": duplicate_status, "timestampsInvented": False},
    }
    validate(result)
    return result


def validate(value: dict[str, Any]) -> None:
    if value.get("schemaVersion") != 1 or value.get("kind") != "MIYORARE_UNIFIED_SOURCE_HEALTH":
        raise ValueError("unsupported unified health schema")
    sources = value.get("sources")
    if not isinstance(sources, list) or value.get("sourceCount") != len(sources):
        raise ValueError("sourceCount does not match sources")
    seen: set[str] = set()
    required = {"canonicalId", "displayName", "language", "packs", "health", "lifecycle", "reasonCodes", "providers", "origin", "lastKnownGood", "lastValidation", "lastCheck", "evidence"}
    for source in sources:
        missing = required - set(source)
        if missing:
            raise ValueError(f"source missing fields: {sorted(missing)}")
        canonical = source["canonicalId"]
        if not isinstance(canonical, str) or not canonical.startswith("miyorare:") or canonical in seen:
            raise ValueError(f"invalid or duplicate canonicalId: {canonical}")
        seen.add(canonical)
        if source["health"] not in HEALTH:
            raise ValueError(f"{canonical}: invalid health")
        if source["lifecycle"] not in LIFECYCLE:
            raise ValueError(f"{canonical}: invalid lifecycle")
        if not isinstance(source["reasonCodes"], list) or not source["reasonCodes"]:
            raise ValueError(f"{canonical}: health requires reasonCodes")
        if not isinstance(source["evidence"], list) or not source["evidence"]:
            raise ValueError(f"{canonical}: health requires evidence")
        if source["lastValidation"].get("checkedAt") is not None or source["lastCheck"].get("checkedAt") is not None:
            raise ValueError(f"{canonical}: P2-A must not invent timestamps")
    obs = value.get("observability", {})
    if obs.get("timestampsInvented") is not False:
        raise ValueError("observability must explicitly state timestamps were not invented")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build_cmd = sub.add_parser("build")
    build_cmd.add_argument("--farm", type=Path, required=True)
    build_cmd.add_argument("--upstream-status", type=Path, required=True)
    build_cmd.add_argument("--canonical-registry", type=Path, required=True)
    build_cmd.add_argument("--output", type=Path, required=True)
    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("--health", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        write(args.output, build(load(args.farm), load(args.upstream_status), load(args.canonical_registry)))
        print(f"Unified source health written to {args.output}")
    else:
        validate(load(args.health))
        print("Unified source health validated")


if __name__ == "__main__":
    main()
