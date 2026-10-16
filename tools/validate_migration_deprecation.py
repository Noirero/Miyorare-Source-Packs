#!/usr/bin/env python3
"""Validate Miyorare source migration/deprecation declarations fail-closed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CONTINUITY = {"preserve", "migrate", "not-applicable"}
CONTINUITY_FIELDS = {"favorites", "history", "progress", "downloads", "aliases"}
APPROVAL = {"PROPOSED", "APPROVED", "REJECTED"}
REMOVAL = {"NOT_REQUESTED", "OWNER_APPROVAL_REQUIRED", "OWNER_APPROVED"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_ids(registry: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for source in registry.get("sources", []):
        canonical = source.get("canonicalId")
        if not isinstance(canonical, str) or not canonical.startswith("miyorare:"):
            raise ValueError("registry contains invalid canonicalId")
        if canonical in ids:
            raise ValueError(f"duplicate canonicalId: {canonical}")
        ids.add(canonical)
    return ids


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_migration(item: dict[str, Any], known: set[str]) -> None:
    required = {"id", "sourceCanonicalId", "targetCanonicalId", "reason", "continuity", "aliases", "lkgPolicy", "evidence", "approval"}
    missing = required - item.keys()
    if missing:
        raise ValueError(f"migration missing fields: {sorted(missing)}")
    source, target = item["sourceCanonicalId"], item["targetCanonicalId"]
    if source not in known or target not in known:
        raise ValueError("migration references unknown canonical identity")
    if source == target:
        raise ValueError("identity migration source and target must differ; domain/provider changes preserve identity")
    if not _nonempty(item["id"]) or not _nonempty(item["reason"]):
        raise ValueError("migration id/reason must be non-empty")
    continuity = item["continuity"]
    if not isinstance(continuity, dict) or set(continuity) != CONTINUITY_FIELDS:
        raise ValueError("migration continuity must explicitly cover favorites/history/progress/downloads/aliases")
    if any(value not in CONTINUITY for value in continuity.values()):
        raise ValueError("migration continuity contains unsupported policy")
    if continuity["aliases"] == "not-applicable":
        raise ValueError("migration aliases continuity may not be not-applicable")
    if not isinstance(item["aliases"], list):
        raise ValueError("migration aliases must be a list")
    if item["lkgPolicy"] != "preserve-until-target-proven":
        raise ValueError("migration must preserve LKG until target is proven")
    if not isinstance(item["evidence"], list) or not item["evidence"]:
        raise ValueError("migration requires evidence")
    if item["approval"] not in APPROVAL:
        raise ValueError("migration approval is invalid")


def validate_deprecation(item: dict[str, Any], known: set[str]) -> None:
    required = {"id", "canonicalId", "reason", "temporaryOutageOnly", "replacementCanonicalId", "aliases", "evidence", "approval", "removal"}
    missing = required - item.keys()
    if missing:
        raise ValueError(f"deprecation missing fields: {sorted(missing)}")
    canonical = item["canonicalId"]
    if canonical not in known:
        raise ValueError("deprecation references unknown canonical identity")
    replacement = item["replacementCanonicalId"]
    if replacement is not None and replacement not in known:
        raise ValueError("deprecation replacement references unknown canonical identity")
    if replacement == canonical:
        raise ValueError("deprecation replacement may not equal canonicalId")
    if not _nonempty(item["id"]) or not _nonempty(item["reason"]):
        raise ValueError("deprecation id/reason must be non-empty")
    if item["temporaryOutageOnly"] is not False:
        raise ValueError("temporary outage alone cannot deprecate a source")
    if not isinstance(item["aliases"], list):
        raise ValueError("deprecation aliases must be a list")
    if not isinstance(item["evidence"], list) or not item["evidence"]:
        raise ValueError("deprecation requires evidence")
    if item["approval"] not in APPROVAL:
        raise ValueError("deprecation approval is invalid")
    removal = item["removal"]
    if removal not in REMOVAL:
        raise ValueError("deprecation removal state is invalid")
    if removal == "OWNER_APPROVED" and item["approval"] != "APPROVED":
        raise ValueError("removal cannot be owner-approved before deprecation approval")


def validate(document: dict[str, Any], registry: dict[str, Any]) -> None:
    if document.get("schemaVersion") != 1 or document.get("kind") != "MIYORARE_SOURCE_MIGRATION_DEPRECATION_STATE":
        raise ValueError("unsupported migration/deprecation state schema")
    known = canonical_ids(registry)
    seen: set[str] = set()
    for item in document.get("migrations", []):
        if item.get("id") in seen:
            raise ValueError("duplicate migration/deprecation id")
        seen.add(item.get("id"))
        validate_migration(item, known)
    for item in document.get("deprecations", []):
        if item.get("id") in seen:
            raise ValueError("duplicate migration/deprecation id")
        seen.add(item.get("id"))
        validate_deprecation(item, known)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    validate(load(args.state), load(args.registry))
    print("migration/deprecation declarations valid")


if __name__ == "__main__":
    main()
