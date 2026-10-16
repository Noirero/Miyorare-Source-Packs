#!/usr/bin/env python3
"""Build/validate Canonical Source Registry V2 without rewriting source identity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_PACKS = {"miyorare-id", "miyorare-en", "miyorare-global"}
LIFECYCLE = {"candidate", "validated", "active", "degraded", "held", "unavailable", "deprecated", "migrated"}
HEALTH = {"HEALTHY", "DEGRADED", "HELD", "UNAVAILABLE", "DEPRECATED", "UNKNOWN"}
PROVIDERS = {"keiyoushi", "uma", "gekkoushi"}
ORIGINS = {"upstream-derived", "miyorare-native", "upstream-overlay"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def validate_pack_list(canonical: str | None, packs: Any) -> list[str]:
    if not isinstance(packs, list) or any(pack not in ALLOWED_PACKS for pack in packs):
        raise ValueError(f"{canonical}: invalid explicit pack membership")
    if len(packs) != len(set(packs)):
        raise ValueError(f"{canonical}: duplicate explicit pack membership")
    return sorted(packs)


def authority_packs(source: dict[str, Any], authority: dict[str, Any] | None, farm_commit: str | None) -> tuple[list[str], str]:
    """Resolve packs from source declaration, else reviewed existing-source authority; never language."""
    if "packs" in source:
        return validate_pack_list(source.get("canonicalId"), source.get("packs")), "source-declaration"
    if authority is None:
        return [], "undeclared"
    if authority.get("schemaVersion") != 1 or authority.get("kind") != "MIYORARE_EXISTING_SOURCE_PACK_AUTHORITY":
        raise ValueError("invalid existing-source pack authority")
    reviewed = authority.get("reviewedFarmCommit")
    if not isinstance(farm_commit, str) or farm_commit != reviewed:
        raise ValueError("existing-source pack authority does not match exact Farm commit")
    canonical = source.get("canonicalId")
    matches = []
    for rule in authority.get("rules", []):
        prefix = rule.get("canonicalPrefix") if isinstance(rule, dict) else None
        if isinstance(canonical, str) and isinstance(prefix, str) and canonical.startswith(prefix):
            matches.append(validate_pack_list(canonical, rule.get("packs")))
    if len(matches) > 1:
        raise ValueError(f"{canonical}: multiple existing-source pack authorities")
    if not matches:
        return [], "undeclared"
    return matches[0], "reviewed-existing-source-authority"


def lifecycle_for(source: dict[str, Any], packs: list[str]) -> str:
    approval = str(source.get("approvalState", "")).upper()
    health = str(source.get("runtimeHealth", "UNKNOWN")).upper()
    if health == "UNAVAILABLE": return "unavailable"
    if health == "DEGRADED": return "degraded"
    if health == "HELD" or approval in {"HELD", "REVIEW_REQUIRED"}: return "held"
    if not packs: return "held"
    if approval == "APPROVED" and source.get("publishEligible") is True: return "active"
    if str(source.get("compatibilityBaseline", {}).get("status", "")).upper() in {"VALIDATED", "PASS", "PASSED"}: return "validated"
    return "candidate"


def health_for(source: dict[str, Any], lifecycle: str, packs: list[str]) -> str:
    if lifecycle == "held" and not packs: return "HELD"
    raw = str(source.get("runtimeHealth", "UNKNOWN")).upper()
    if raw in HEALTH: return raw
    if lifecycle == "held": return "HELD"
    if lifecycle == "unavailable": return "UNAVAILABLE"
    if lifecycle == "degraded": return "DEGRADED"
    return "UNKNOWN"


def explicit_origin(source: dict[str, Any]) -> dict[str, Any]:
    declared = source.get("origin")
    if declared is not None:
        if not isinstance(declared, dict) or declared.get("kind") not in ORIGINS:
            raise ValueError(f"{source.get('canonicalId')}: invalid explicit origin")
        providers = declared.get("providers", [])
        if not isinstance(providers, list) or any(provider not in PROVIDERS for provider in providers):
            raise ValueError(f"{source.get('canonicalId')}: invalid explicit origin providers")
        result = dict(declared); result["providers"] = sorted(set(providers)); result["authority"] = "source-declaration"
        return result
    identities = source.get("upstreamIdentities")
    if not isinstance(identities, dict) or not identities:
        raise ValueError(f"{source.get('canonicalId')}: origin requires explicit declaration or upstream identity evidence")
    providers = sorted(provider for provider in identities if provider in PROVIDERS)
    if not providers:
        raise ValueError(f"{source.get('canonicalId')}: legacy origin evidence has no recognized provider")
    overlays = source.get("protectedOverlays", [])
    result: dict[str, Any] = {"kind": "upstream-overlay" if overlays else "upstream-derived", "providers": providers, "authority": "legacy-upstream-identities"}
    if overlays: result["protectedOverlays"] = overlays
    return result


def migrate(farm: dict[str, Any], pack_authority: dict[str, Any] | None = None, farm_commit: str | None = None) -> dict[str, Any]:
    if farm.get("schemaVersion") != 1: raise ValueError("P1-A migration currently accepts Farm schemaVersion 1 only")
    sources = []
    for old in farm.get("sources", []):
        canonical = old.get("canonicalId")
        if not isinstance(canonical, str) or not canonical.startswith("miyorare:"):
            raise ValueError("refusing to invent or rewrite an invalid canonicalId")
        packs, pack_authority_kind = authority_packs(old, pack_authority, farm_commit)
        lifecycle = lifecycle_for(old, packs)
        identities = old.get("upstreamIdentities", {})
        if not isinstance(identities, dict): identities = {}
        providers = {name: mapping for name, mapping in identities.items() if name in PROVIDERS and isinstance(mapping, dict)}
        source = {
            "canonicalId": canonical,
            "displayName": old.get("displayName") or canonical.rsplit(":", 1)[-1],
            "language": str(old.get("language", "unknown")).lower(),
            "packs": packs,
            "packAuthority": pack_authority_kind,
            "origin": explicit_origin(old),
            "providers": providers,
            "lifecycle": {"state": lifecycle, "ownerActionRequired": bool(old.get("ownerActionRequired", False)) or not packs, "reason": "PACK_MEMBERSHIP_UNDECLARED" if not packs else None},
            "compatibility": {"health": health_for(old, lifecycle, packs), "baseline": old.get("compatibilityBaseline", {}), "lastKnownGood": old.get("lastKnownGood", {}), "currentVersion": old.get("currentVersion", {})},
        }
        sources.append(source)
    result = {
        "schemaVersion": 2,
        "kind": "MIYORARE_CANONICAL_SOURCE_REGISTRY",
        "migration": {"fromSchemaVersion": 1, "identityPreserved": True, "packMembershipAuthority": "source-declaration-or-reviewed-existing-source-authority", "languageInferenceDisabled": True, "originAuthority": "source-declaration-or-legacy-upstream-identity-evidence", "reviewedFarmCommit": pack_authority.get("reviewedFarmCommit") if pack_authority else None},
        "providerBaselines": farm.get("providerBaselines", {}),
        "sources": sorted(sources, key=lambda item: item["canonicalId"]),
    }
    validate(result); return result


def validate(value: dict[str, Any]) -> None:
    if value.get("schemaVersion") != 2 or value.get("kind") != "MIYORARE_CANONICAL_SOURCE_REGISTRY": raise ValueError("unsupported canonical source registry schema")
    seen: set[str] = set(); provider_seen: set[tuple[str, str]] = set()
    for source in value.get("sources", []):
        canonical = source.get("canonicalId")
        if not isinstance(canonical, str) or not canonical.startswith("miyorare:") or canonical in seen: raise ValueError(f"invalid or duplicate canonicalId: {canonical}")
        seen.add(canonical)
        packs = validate_pack_list(canonical, source.get("packs"))
        if source.get("packAuthority") not in {"source-declaration", "reviewed-existing-source-authority", "undeclared", None}: raise ValueError(f"{canonical}: invalid pack authority")
        origin = source.get("origin", {})
        if origin.get("kind") not in ORIGINS or origin.get("authority") not in {"source-declaration", "legacy-upstream-identities"}: raise ValueError(f"{canonical}: invalid or unauthoritative origin")
        lifecycle = source.get("lifecycle", {}).get("state")
        if lifecycle not in LIFECYCLE: raise ValueError(f"{canonical}: invalid lifecycle")
        if not packs and (lifecycle != "held" or source.get("compatibility", {}).get("health") != "HELD"): raise ValueError(f"{canonical}: undeclared pack membership must fail closed as HELD")
        if source.get("compatibility", {}).get("health") not in HEALTH: raise ValueError(f"{canonical}: invalid compatibility health")
        providers = source.get("providers")
        if not isinstance(providers, dict): raise ValueError(f"{canonical}: providers must be an object")
        for provider, mapping in providers.items():
            if provider not in PROVIDERS or not isinstance(mapping, dict): raise ValueError(f"{canonical}: invalid provider mapping")
            key = (provider, json.dumps(mapping, sort_keys=True, separators=(",", ":")))
            if key in provider_seen: raise ValueError(f"provider identity belongs to multiple canonical sources: {provider}")
            provider_seen.add(key)


def main() -> None:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    migration = sub.add_parser("migrate"); migration.add_argument("--farm", type=Path, required=True); migration.add_argument("--output", type=Path, required=True); migration.add_argument("--pack-authority", type=Path); migration.add_argument("--farm-commit")
    validation = sub.add_parser("validate"); validation.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "migrate": write(args.output, migrate(load(args.farm), load(args.pack_authority) if args.pack_authority else None, args.farm_commit))
    else: validate(load(args.registry)); print("Canonical Source Registry V2 validated")


if __name__ == "__main__": main()
