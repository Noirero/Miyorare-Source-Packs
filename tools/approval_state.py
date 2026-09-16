#!/usr/bin/env python3
"""Candidate approval proofs for Miyorare approve-only maintenance.

This module deliberately does not mutate upstream registry state, sign artifacts, publish,
or promote last-known-good revisions. It stages an exact validated candidate set, records an
explicit approval bound to that set, and emits promotion authorization only when the registry,
candidate SHAs, and authoritative evidence bindings are still unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ApprovalStateError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ApprovalStateError(f"{path} must contain a JSON object")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value.lower()):
        raise ApprovalStateError(f"{name} must be a 40-character git SHA")
    return value.lower()


def _digest64(value: Any, name: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value.lower()):
        raise ApprovalStateError(f"{name} must be a SHA-256 digest")
    return value.lower()


def validate_evidence_binding(binding: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(binding, dict):
        raise ApprovalStateError("evidence binding must be an object")
    if binding.get("schemaVersion") != 1:
        raise ApprovalStateError("evidence binding schemaVersion must be 1")
    normalized = {
        "schemaVersion": 1,
        "farmEvidenceSha256": _digest64(binding.get("farmEvidenceSha256"), "evidence farmEvidenceSha256"),
        "gateSha256": _digest64(binding.get("gateSha256"), "evidence gateSha256"),
        "repairEvidenceSha256": _digest64(binding.get("repairEvidenceSha256"), "evidence repairEvidenceSha256"),
    }
    repair_count = binding.get("repairEvidenceCount")
    if not isinstance(repair_count, int) or isinstance(repair_count, bool) or repair_count < 0:
        raise ApprovalStateError("evidence repairEvidenceCount must be a non-negative integer")
    normalized["repairEvidenceCount"] = repair_count
    return normalized


def validate_waiting_gate(gate: dict[str, Any]) -> None:
    expected = {
        "maintenanceMode": "APPROVE_ONLY",
        "candidateMode": True,
        "updateState": "CANDIDATE",
        "approvalState": "WAITING_FOR_APPROVAL",
        "releaseGate": "WAITING_FOR_APPROVAL",
        "nextAction": "WAIT_FOR_APPROVAL",
        "ownerActionRequired": False,
        "publishEligible": False,
    }
    for key, value in expected.items():
        if gate.get(key) != value:
            raise ApprovalStateError(f"candidate gate {key} must be {value!r}")
    evidence = gate.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("candidatePass") is not True:
        raise ApprovalStateError("candidate gate requires passing Compatibility Farm evidence")
    coverage = evidence.get("coverage")
    if not isinstance(coverage, dict):
        raise ApprovalStateError("candidate gate coverage is required")
    if coverage.get("fullCanonicalCoverage") is not True:
        raise ApprovalStateError("candidate gate requires full canonical coverage")
    if coverage.get("fullProviderMembershipCoverage") is not True:
        raise ApprovalStateError("candidate gate requires full provider membership coverage")


def build_pending(
    registry: dict[str, Any],
    plan: dict[str, Any],
    gate: dict[str, Any],
    evidence_binding: dict[str, Any],
) -> dict[str, Any]:
    validate_waiting_gate(gate)
    binding = validate_evidence_binding(evidence_binding)
    if plan.get("schema") != 1 or not isinstance(plan.get("providers"), dict):
        raise ApprovalStateError("sync plan schema/providers are invalid")
    registry_providers = registry.get("providers")
    if not isinstance(registry_providers, dict):
        raise ApprovalStateError("registry.providers must be an object")

    candidates: dict[str, dict[str, str]] = {}
    for provider, item in sorted(plan["providers"].items()):
        if not isinstance(item, dict):
            raise ApprovalStateError(f"plan provider {provider} must be an object")
        if item.get("changed") is not True:
            continue
        registry_provider = registry_providers.get(provider)
        if not isinstance(registry_provider, dict):
            raise ApprovalStateError(f"unknown provider in sync plan: {provider}")
        current = _sha(item.get("lastKnownGood"), f"plan.providers.{provider}.lastKnownGood")
        candidate = _sha(item.get("candidate"), f"plan.providers.{provider}.candidate")
        registry_lkg = _sha(registry_provider.get("lastKnownGood"), f"registry.providers.{provider}.lastKnownGood")
        if current != registry_lkg:
            raise ApprovalStateError(f"{provider} plan is stale: lastKnownGood changed")
        if candidate == current:
            raise ApprovalStateError(f"{provider} is marked changed but candidate equals current")
        candidates[provider] = {
            "current": current,
            "candidate": candidate,
            "state": "WAITING_FOR_APPROVAL",
        }

    if not candidates:
        raise ApprovalStateError("no changed validated candidates to stage")

    gate_fingerprint = _digest(gate)
    identity = {
        "providers": {
            provider: {"current": item["current"], "candidate": item["candidate"]}
            for provider, item in candidates.items()
        },
        "gateFingerprint": gate_fingerprint,
        "evidenceBinding": binding,
    }
    candidate_set_id = _digest(identity)
    return {
        "schemaVersion": 1,
        "maintenanceMode": "APPROVE_ONLY",
        "state": "WAITING_FOR_APPROVAL",
        "candidateSetId": candidate_set_id,
        "gateFingerprint": gate_fingerprint,
        "evidenceBinding": binding,
        "providers": candidates,
        "ownerActionRequired": False,
        "publishEligible": False,
    }


def validate_pending(pending: dict[str, Any]) -> None:
    if pending.get("schemaVersion") != 1:
        raise ApprovalStateError("pending approval schemaVersion must be 1")
    if pending.get("maintenanceMode") != "APPROVE_ONLY":
        raise ApprovalStateError("pending approval must use APPROVE_ONLY")
    if pending.get("state") != "WAITING_FOR_APPROVAL":
        raise ApprovalStateError("pending approval state must be WAITING_FOR_APPROVAL")
    candidate_set_id = pending.get("candidateSetId")
    if not isinstance(candidate_set_id, str) or not HEX64.fullmatch(candidate_set_id):
        raise ApprovalStateError("pending candidateSetId must be a SHA-256 digest")
    if pending.get("publishEligible") is not False:
        raise ApprovalStateError("pending candidate must not be publish eligible")
    providers = pending.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ApprovalStateError("pending providers must be non-empty")
    identity_providers: dict[str, dict[str, str]] = {}
    for provider, item in sorted(providers.items()):
        if not isinstance(item, dict) or item.get("state") != "WAITING_FOR_APPROVAL":
            raise ApprovalStateError(f"pending provider {provider} has invalid state")
        current = _sha(item.get("current"), f"pending.providers.{provider}.current")
        candidate = _sha(item.get("candidate"), f"pending.providers.{provider}.candidate")
        identity_providers[provider] = {"current": current, "candidate": candidate}
    gate_fingerprint = pending.get("gateFingerprint")
    if not isinstance(gate_fingerprint, str) or not HEX64.fullmatch(gate_fingerprint):
        raise ApprovalStateError("pending gateFingerprint must be a SHA-256 digest")
    binding = validate_evidence_binding(pending.get("evidenceBinding"))
    expected_id = _digest(
        {
            "providers": identity_providers,
            "gateFingerprint": gate_fingerprint,
            "evidenceBinding": binding,
        }
    )
    if candidate_set_id != expected_id:
        raise ApprovalStateError("pending candidateSetId does not match candidate contents or evidence")


def approve_pending(pending: dict[str, Any], candidate_set_id: str, actor: str) -> dict[str, Any]:
    validate_pending(pending)
    if not isinstance(actor, str) or not actor.strip():
        raise ApprovalStateError("approval actor is required")
    if candidate_set_id != pending["candidateSetId"]:
        raise ApprovalStateError("approval candidateSetId does not match pending candidate")
    return {
        "schemaVersion": 1,
        "maintenanceMode": "APPROVE_ONLY",
        "approvalState": "APPROVED",
        "candidateSetId": pending["candidateSetId"],
        "approvedBy": actor.strip(),
        "gateFingerprint": pending["gateFingerprint"],
        "evidenceBinding": deepcopy(pending["evidenceBinding"]),
        "providers": {
            provider: item["candidate"] for provider, item in sorted(pending["providers"].items())
        },
        "publishEligible": False,
    }


def authorize_promotion(
    registry: dict[str, Any],
    pending: dict[str, Any],
    approval: dict[str, Any],
    provider: str,
    commit: str,
) -> dict[str, Any]:
    validate_pending(pending)
    if approval.get("schemaVersion") != 1 or approval.get("approvalState") != "APPROVED":
        raise ApprovalStateError("approval proof must be APPROVED schemaVersion 1")
    if approval.get("maintenanceMode") != "APPROVE_ONLY":
        raise ApprovalStateError("approval proof must use APPROVE_ONLY")
    if approval.get("candidateSetId") != pending["candidateSetId"]:
        raise ApprovalStateError("approval proof belongs to a different candidate set")
    if approval.get("gateFingerprint") != pending["gateFingerprint"]:
        raise ApprovalStateError("approval gate fingerprint does not match pending candidate")
    if approval.get("evidenceBinding") != pending["evidenceBinding"]:
        raise ApprovalStateError("approval evidence binding does not match pending candidate")
    approved_by = approval.get("approvedBy")
    if not isinstance(approved_by, str) or not approved_by:
        raise ApprovalStateError("approval proof is missing approvedBy")

    item = pending["providers"].get(provider)
    if not isinstance(item, dict):
        raise ApprovalStateError(f"provider {provider} is not part of the approved candidate set")
    requested = _sha(commit, "promotion commit")
    if requested != item["candidate"]:
        raise ApprovalStateError(f"provider {provider} promotion SHA does not match approved candidate")
    approved_providers = approval.get("providers")
    if not isinstance(approved_providers, dict) or approved_providers.get(provider) != requested:
        raise ApprovalStateError(f"provider {provider} approval SHA does not match pending candidate")

    registry_provider = registry.get("providers", {}).get(provider)
    if not isinstance(registry_provider, dict):
        raise ApprovalStateError(f"unknown registry provider: {provider}")
    current_lkg = _sha(registry_provider.get("lastKnownGood"), f"registry.providers.{provider}.lastKnownGood")
    if current_lkg != item["current"]:
        raise ApprovalStateError(f"provider {provider} registry changed after staging; approval is stale")

    return {
        "schemaVersion": 1,
        "authorized": True,
        "maintenanceMode": "APPROVE_ONLY",
        "candidateSetId": pending["candidateSetId"],
        "provider": provider,
        "expectedCurrent": item["current"],
        "commit": requested,
        "approvedBy": approved_by,
        "gateFingerprint": pending["gateFingerprint"],
        "evidenceBinding": deepcopy(pending["evidenceBinding"]),
        "publishEligible": False,
    }


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage")
    stage.add_argument("--registry", required=True)
    stage.add_argument("--plan", required=True)
    stage.add_argument("--gate", required=True)
    stage.add_argument("--evidence-binding", required=True)
    stage.add_argument("--output", required=True, type=Path)
    approve = sub.add_parser("approve")
    approve.add_argument("--pending", required=True)
    approve.add_argument("--candidate-set-id", required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--output", required=True, type=Path)
    authorize = sub.add_parser("authorize")
    authorize.add_argument("--registry", required=True)
    authorize.add_argument("--pending", required=True)
    authorize.add_argument("--approval", required=True)
    authorize.add_argument("--provider", required=True)
    authorize.add_argument("--commit", required=True)
    authorize.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "stage":
            value = build_pending(
                load_json(args.registry),
                load_json(args.plan),
                load_json(args.gate),
                load_json(args.evidence_binding),
            )
        elif args.command == "approve":
            value = approve_pending(load_json(args.pending), args.candidate_set_id, args.actor)
        elif args.command == "authorize":
            value = authorize_promotion(
                load_json(args.registry), load_json(args.pending), load_json(args.approval), args.provider, args.commit
            )
        else:
            raise AssertionError(args.command)
        _write(args.output, value)
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    except (ApprovalStateError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
