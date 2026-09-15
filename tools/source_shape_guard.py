#!/usr/bin/env python3
"""Validate deterministic fixture sources against pinned upstream Kotlin source shape.

This is a structural guard, not a substitute for behavioral parser execution. It verifies
that a fixture still points at the registered upstream file and that the source preserves
family-level parser/auth/header signals expected by the Compatibility Farm.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class ShapeError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ShapeError(f"{path} must contain a JSON object")
    return value


def _index_sources(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = registry.get("sources")
    if not isinstance(sources, list):
        raise ShapeError("registry.sources must be a list")
    result = {}
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("canonicalId"), str):
            raise ShapeError("invalid source registry entry")
        result[source["canonicalId"]] = source
    return result


def validate_shapes(
    registry: dict[str, Any],
    fixtures: dict[str, Any],
    families: dict[str, Any],
    provider: str,
    root: Path,
) -> dict[str, Any]:
    if families.get("schemaVersion") != 1:
        raise ShapeError("adapter family schemaVersion must be 1")
    family_map = families.get("families")
    if not isinstance(family_map, dict) or not family_map:
        raise ShapeError("adapter family contracts are required")

    registry_sources = _index_sources(registry)
    fixture_sources = fixtures.get("sources")
    if not isinstance(fixture_sources, list) or not fixture_sources:
        raise ShapeError("fixture sources must be a non-empty list")

    results = []
    checked = 0
    for fixture in fixture_sources:
        canonical_id = fixture.get("canonicalId")
        source = registry_sources.get(canonical_id)
        if source is None:
            raise ShapeError(f"fixture source is not registered: {canonical_id}")
        identities = source.get("upstreamIdentities")
        if not isinstance(identities, dict) or provider not in identities:
            continue
        identity = identities[provider]
        if not isinstance(identity, dict):
            raise ShapeError(f"{canonical_id}: invalid {provider} identity")
        relative = identity.get("file")
        source_name = identity.get("sourceName")
        if not isinstance(relative, str) or not relative.endswith(".kt"):
            raise ShapeError(f"{canonical_id}: {provider} identity requires Kotlin file path")
        if not isinstance(source_name, str) or not source_name:
            raise ShapeError(f"{canonical_id}: {provider} identity requires sourceName")

        family_name = source.get("adapterFamily")
        family = family_map.get(family_name)
        if not isinstance(family, dict):
            raise ShapeError(f"{canonical_id}: no shape contract for adapter family {family_name!r}")
        groups = family.get("requiredTokenGroups")
        if not isinstance(groups, list) or not groups:
            raise ShapeError(f"{family_name}: requiredTokenGroups must be non-empty")

        path = root / relative
        if not path.is_file():
            raise ShapeError(f"{canonical_id}: upstream source file missing: {relative}")
        text = path.read_text(encoding="utf-8")

        missing_groups: list[list[str]] = []
        for group in groups:
            if not isinstance(group, list) or not group or not all(isinstance(token, str) and token for token in group):
                raise ShapeError(f"{family_name}: invalid required token group")
            if not any(token in text for token in group):
                missing_groups.append(group)

        annotation_token = f'@MangaSourceParser("{source_name}"'
        identity_ok = annotation_token in text
        status = "PASS" if identity_ok and not missing_groups else "FAIL"
        results.append(
            {
                "canonicalId": canonical_id,
                "provider": provider,
                "file": relative,
                "adapterFamily": family_name,
                "identityAnnotation": identity_ok,
                "missingTokenGroups": missing_groups,
                "status": status,
            }
        )
        checked += 1

    if checked == 0:
        raise ShapeError(f"no fixture sources are backed by provider {provider}")

    failed = sum(item["status"] != "PASS" for item in results)
    return {
        "schemaVersion": 1,
        "provider": provider,
        "checked": checked,
        "failed": failed,
        "status": "PASS" if failed == 0 else "FAIL",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="compatibility/source-registry.json")
    parser.add_argument("--fixtures", default="compatibility/fixtures/deterministic-seed-8.json")
    parser.add_argument("--families", default="compatibility/adapter-families.json")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        report = validate_shapes(
            load_json(args.registry),
            load_json(args.fixtures),
            load_json(args.families),
            args.provider,
            args.root,
        )
        rendered = json.dumps(report, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
        return 0 if report["status"] == "PASS" else 2
    except (ShapeError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
