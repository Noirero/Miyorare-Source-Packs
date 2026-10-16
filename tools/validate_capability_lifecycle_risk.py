#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CAPABILITIES = {"browse", "latest", "search", "filters", "details", "chapters", "pages", "download", "authentication", "migration", "webview", "challenge"}
CAPABILITY_STATES = {"SUPPORTED", "UNSUPPORTED", "UNKNOWN"}
LIFECYCLE = {"candidate", "validated", "active", "degraded", "held", "unavailable", "deprecated", "migrated"}
RISK = {"LOW", "MEDIUM", "HIGH", "VERY_HIGH", "UNKNOWN"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(value: dict[str, Any]) -> None:
    if value.get("schemaVersion") != 1 or value.get("kind") != "MIYORARE_SOURCE_CAPABILITY_LIFECYCLE_RISK_CONTRACT":
        raise ValueError("unsupported P1-B contract")
    if set(value.get("capabilities", {}).get("known", [])) != CAPABILITIES:
        raise ValueError("capability vocabulary drift")
    if set(value.get("capabilities", {}).get("states", [])) != CAPABILITY_STATES:
        raise ValueError("capability state vocabulary drift")
    if set(value.get("lifecycle", {}).get("states", [])) != LIFECYCLE:
        raise ValueError("lifecycle vocabulary must match Canonical Source Registry V2")
    transitions = value.get("lifecycle", {}).get("transitions", {})
    if set(transitions) != LIFECYCLE:
        raise ValueError("every lifecycle state needs an explicit transition set")
    for state, targets in transitions.items():
        if not isinstance(targets, list) or any(target not in LIFECYCLE for target in targets):
            raise ValueError(f"invalid lifecycle transition from {state}")
    levels = set(value.get("risk", {}).get("levels", []))
    if levels != RISK:
        raise ValueError("risk vocabulary drift")
    for name, level in value.get("risk", {}).get("classes", {}).items():
        if level not in RISK:
            raise ValueError(f"invalid risk class {name}: {level}")
    evidence = value.get("validation", {}).get("riskMinimumEvidence", {})
    if set(evidence) != RISK:
        raise ValueError("every risk level requires explicit minimum evidence")
    if evidence.get("UNKNOWN") != ["hold-for-classification"]:
        raise ValueError("UNKNOWN risk must fail closed")


def validate_registry(registry: dict[str, Any]) -> None:
    if registry.get("schemaVersion") != 2 or registry.get("kind") != "MIYORARE_CANONICAL_SOURCE_REGISTRY":
        raise ValueError("expected Canonical Source Registry V2")
    for source in registry.get("sources", []):
        state = source.get("lifecycle", {}).get("state")
        if state not in LIFECYCLE:
            raise ValueError(f"{source.get('canonicalId')}: lifecycle outside P1-B contract")
        capabilities = source.get("capabilities")
        risk = source.get("risk")
        # P1-B is additive. P1-A projections remain valid until capability/risk evidence is populated.
        if capabilities is not None:
            if not isinstance(capabilities, dict):
                raise ValueError(f"{source.get('canonicalId')}: capabilities must be an object")
            for name, status in capabilities.items():
                if name not in CAPABILITIES or status not in CAPABILITY_STATES:
                    raise ValueError(f"{source.get('canonicalId')}: invalid capability {name}={status}")
        if risk is not None:
            if not isinstance(risk, dict) or risk.get("level") not in RISK:
                raise ValueError(f"{source.get('canonicalId')}: invalid risk")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    validate_contract(load(args.contract))
    if args.registry:
        validate_registry(load(args.registry))
    print("P1-B capability/lifecycle/risk contract validated")


if __name__ == "__main__":
    main()
