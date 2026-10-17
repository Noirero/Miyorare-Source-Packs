#!/usr/bin/env python3
"""Build approval artifacts for the exact runtime-proven Source Lab subset.

The provider-wide runtime disposition remains HELD when any source is blocked. This helper
creates a separate approve-only candidate identity only for sources already proven COMPATIBLE
by the runtime gate. Blocked sources are explicitly excluded and remain fail-closed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")


class ScopedApprovalError(ValueError):
    pass


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ScopedApprovalError(f"{path} must contain a JSON object")
    return value


def build(runtime_gate: dict[str, Any], disposition: dict[str, Any], provider: str) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = runtime_gate.get("candidate")
    compatible = runtime_gate.get("compatible")
    blocked = runtime_gate.get("infrastructureBlocked")
    if runtime_gate.get("schemaVersion") != 1 or not isinstance(candidate, str) or not HEX40.fullmatch(candidate):
        raise ScopedApprovalError("runtime gate candidate identity is invalid")
    if runtime_gate.get("state") != "HELD" or runtime_gate.get("candidateFarmAllowed") is not False:
        raise ScopedApprovalError("runtime gate must preserve provider-wide HELD state")
    if not isinstance(compatible, list) or not compatible or len(compatible) != len(set(compatible)):
        raise ScopedApprovalError("runtime gate compatible scope must be non-empty and unique")
    if not isinstance(blocked, list) or not blocked or set(compatible) & set(blocked):
        raise ScopedApprovalError("runtime gate blocked scope must remain non-empty and disjoint")
    if compatible != sorted(compatible) or blocked != sorted(blocked):
        raise ScopedApprovalError("runtime gate source membership must be canonical")
    if disposition.get("candidate") != candidate or disposition.get("state") != "hold":
        raise ScopedApprovalError("runtime disposition does not match held candidate")

    sources = disposition.get("sources")
    if not isinstance(sources, list):
        raise ScopedApprovalError("runtime disposition sources are missing")
    index = {item.get("canonicalId"): item for item in sources if isinstance(item, dict)}
    for canonical in compatible:
        item = index.get(canonical)
        evidence = item.get("evidenceDisposition") if isinstance(item, dict) else None
        if not isinstance(item, dict) or item.get("automationClass") != "REVIEWED_COMPATIBLE":
            raise ScopedApprovalError(f"{canonical}: compatible scope is not runtime-reviewed")
        if not isinstance(evidence, dict) or evidence.get("candidate") != candidate or evidence.get("evidenceType") != "runtime-closure-execution":
            raise ScopedApprovalError(f"{canonical}: exact runtime evidence is missing")
    for canonical in blocked:
        item = index.get(canonical)
        if not isinstance(item, dict) or item.get("automationClass") != "NEEDS_REVIEW" or item.get("evidenceDisposition") is not None:
            raise ScopedApprovalError(f"{canonical}: blocked source no longer fails closed")

    scope = {provider: compatible}
    aggregate = {
        "schemaVersion": 1,
        "evidenceType": "runtime-closure-execution",
        "candidate": candidate,
        "parserExecution": True,
        "candidatePass": True,
        "sourceScope": scope,
        "compatible": compatible,
        "excludedInfrastructureBlocked": blocked,
        "providerWideState": "HELD",
        "repairEvidence": {"reportedMemberships": 0},
    }
    gate = {
        "schemaVersion": 1,
        "maintenanceMode": "APPROVE_ONLY",
        "candidateMode": True,
        "updateState": "CANDIDATE",
        "approvalState": "WAITING_FOR_APPROVAL",
        "releaseGate": "WAITING_FOR_APPROVAL",
        "nextAction": "WAIT_FOR_APPROVAL",
        "ownerActionRequired": False,
        "publishEligible": False,
        "sourceScope": scope,
        "providerWideState": "HELD",
        "excludedInfrastructureBlocked": blocked,
        "evidence": {
            "candidatePass": True,
            "evidenceType": "runtime-closure-execution",
            "coverage": {
                "coverageUniverse": "sourceScope",
                "fullCanonicalCoverage": True,
                "fullProviderMembershipCoverage": True,
                "sourceCount": len(compatible),
            },
        },
    }
    return aggregate, gate


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-gate", type=Path, required=True)
    parser.add_argument("--disposition", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--aggregate-output", type=Path, required=True)
    parser.add_argument("--gate-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        aggregate, gate = build(load(args.runtime_gate), load(args.disposition), args.provider)
        write(args.aggregate_output, aggregate)
        write(args.gate_output, gate)
        print(json.dumps({"sourceScope": gate["sourceScope"], "providerWideState": "HELD"}, sort_keys=True))
        return 0
    except (ScopedApprovalError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
