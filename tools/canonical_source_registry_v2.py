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


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def pack_for(language: str) -> list[str]:
    if language == "id":
        return ["miyorare-id"]
    if language == "en":
        return ["miyorare-en"]
    return []


def lifecycle_for(source: dict[str, Any]) -> str:
    approval = str(source.get("approvalState", "")).upper()
    health = str(source.get("runtimeHealth", "UNKNOWN")).upper()
    if health == "UNAVAILABLE":
        return "unavailable"
    if health == "DEGRADED":
        return "degraded"
    if health == "HELD" or approval in {"HELD", "REVIEW_REQUIRED"}:
        return "held"
    if approval == "APPROVED" and source.get("publishEligible") is True:
        return "active"
    if str(source.get("compatibilityBaseline", {}).get("status", "")).upper() in {"VALIDATED", "PASS", "PASSED"}:
        return "validated"
    return "candidate"


def health_for(source: dict[str, Any], lifecycle: str) -> str:
    raw = str(source.get("runtimeHealth", "UNKNOWN")).upper()
    if raw in HEALTH:
        return raw
    if lifecycle == "held":
        return "HELD"
    if lifecycle == "unavailable":
        return "UNAVAILABLE"
    if lifecycle == "degraded":
        return "DEGRADED"
    return "UNKNOWN"


def origin_for(source: dict[str, Any]) -> dict[str, Any]:
    providers = sorted(p for p in source.get("providers", []) if p in PROVIDERS)
    overlays = source.get("protectedOverlays", [])
    kind = "upstream-overlay" if overlays else "upstream-derived"
    return {"kind": kind, "providers": providers}


def migrate(farm: dict[str, Any]) -> dict[str, Any]:
    if farm.get("schemaVersion") != 1:
        raise ValueError("P1-A migration currently accepts Farm schemaVersion 1 only")
    sources = []
    for old in farm.get("sources", []):
        canonical = old.get("canonicalId")
        if not isinstance(canonical, str) or not canonical.startswith("miyorare:"):
            raise ValueError("refusing to invent or rewrite an invalid canonicalId")
        language = str(old.get("language", "unknown")).lower()
        lifecycle = lifecycle_for(old)
        identities = old.get("upstreamIdentities", {})
        if not isinstance(identities, dict):
            identities = {}
        providers = {name: mapping for name, mapping in identities.items() if name in PROVIDERS and isinstance(mapping, dict)}
        source = {
            "canonicalId": canonical,
            "displayName": old.get("displayName") or canonical.rsplit(":", 1)[-1],
            "language": language,
            "packs": pack_for(language),
            "origin": origin_for(old),
            "providers": providers,
            "lifecycle": {"state": lifecycle, "ownerActionRequired": bool(old.get("ownerActionRequired", False))},
            "compatibility": {
                "health": health_for(old, lifecycle),
                "baseline": old.get("compatibilityBaseline", {}),
                "lastKnownGood": old.get("lastKnownGood", {}),
                "currentVersion": old.get("currentVersion", {}),
            },
        }
        if old.get("protectedOverlays"):
            source["origin"]["protectedOverlays"] = old["protectedOverlays"]
        sources.append(source)
    result = {
        "schemaVersion": 2,
        "kind": "MIYORARE_CANONICAL_SOURCE_REGISTRY",
        "migration": {"fromSchemaVersion": 1, "identityPreserved": True},
        "providerBaselines": farm.get("providerBaselines", {}),
        "sources": sorted(sources, key=lambda item: item["canonicalId"]),
    }
    validate(result)
    return result


def validate(value: dict[str, Any]) -> None:
    if value.get("schemaVersion") != 2 or value.get("kind") != "MIYORARE_CANONICAL_SOURCE_REGISTRY":
        raise ValueError("unsupported canonical source registry schema")
    seen: set[str] = set()
    provider_seen: set[tuple[str, str]] = set()
    for source in value.get("sources", []):
        canonical = source.get("canonicalId")
        if not isinstance(canonical, str) or not canonical.startswith("miyorare:") or canonical in seen:
            raise ValueError(f"invalid or duplicate canonicalId: {canonical}")
        seen.add(canonical)
        packs = source.get("packs")
        if not isinstance(packs, list) or any(pack not in ALLOWED_PACKS for pack in packs):
            raise ValueError(f"{canonical}: invalid pack membership")
        origin = source.get("origin", {})
        if origin.get("kind") not in {"upstream-derived", "miyorare-native", "upstream-overlay"}:
            raise ValueError(f"{canonical}: invalid origin")
        lifecycle = source.get("lifecycle", {}).get("state")
        if lifecycle not in LIFECYCLE:
            raise ValueError(f"{canonical}: invalid lifecycle")
        health = source.get("compatibility", {}).get("health")
        if health not in HEALTH:
            raise ValueError(f"{canonical}: invalid compatibility health")
        providers = source.get("providers")
        if not isinstance(providers, dict):
            raise ValueError(f"{canonical}: providers must be an object")
        for provider, mapping in providers.items():
            if provider not in PROVIDERS or not isinstance(mapping, dict):
                raise ValueError(f"{canonical}: invalid provider mapping")
            identity = json.dumps(mapping, sort_keys=True, separators=(",", ":"))
            key = (provider, identity)
            if key in provider_seen:
                raise ValueError(f"provider identity belongs to multiple canonical sources: {provider}")
            provider_seen.add(key)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    migration = sub.add_parser("migrate")
    migration.add_argument("--farm", type=Path, required=True)
    migration.add_argument("--output", type=Path, required=True)
    validation = sub.add_parser("validate")
    validation.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "migrate":
        write(args.output, migrate(load(args.farm)))
    else:
        validate(load(args.registry))
        print("Canonical Source Registry V2 validated")


if __name__ == "__main__":
    main()
