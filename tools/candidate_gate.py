#!/usr/bin/env python3
"""Turn trustworthy Compatibility Farm aggregate evidence into an approve-only gate.

This module does not publish, promote, sign, or mutate source registry state. It bridges
real-parser coverage evidence to the provider-neutral compatibility contract evaluator.
Incomplete coverage remains a safe NOT_READY candidate, while a fully exercised passing
candidate becomes WAITING_FOR_APPROVAL automatically.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compatibility_contract import ContractError, evaluate_candidate, load_json, validate_contract


class CandidateGateError(ValueError):
    pass


PARTIAL_GATES = {
    "NOT_READY_PARTIAL_PARSER_HARNESS",
    "NOT_READY_PARTIAL_COVERAGE",
    "NOT_READY_NO_PARSER_HARNESS",
}


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise CandidateGateError(f"{name} must be boolean")
    return value


def _context(context: dict[str, Any] | None) -> dict[str, Any]:
    value = dict(context or {})
    value.setdefault("currentRuntimeHealth", "UNKNOWN")
    value.setdefault("regressionDetected", False)
    value.setdefault("safeFallbackAvailable", True)
    value.setdefault("selfRepairExhausted", False)
    value.setdefault("approvalState", "NOT_READY")
    return value


def validate_aggregate(aggregate: dict[str, Any]) -> None:
    if aggregate.get("executionMode") not in {
        "real-kotlin-parser-aggregate",
        "real-kotlin-parser-maintenance-evidence",
    }:
        raise CandidateGateError("aggregate must come from real Kotlin parser aggregation")
    if aggregate.get("parserExecution") is not True:
        raise CandidateGateError("aggregate.parserExecution must be true")
    if aggregate.get("publishEligible") is not False:
        raise CandidateGateError("aggregate must never be publish eligible")
    if aggregate.get("ownerActionRequired") is not False:
        raise CandidateGateError("aggregate must not assign routine work to the owner")
    if not isinstance(aggregate.get("candidatePass"), bool):
        raise CandidateGateError("aggregate.candidatePass must be boolean")
    if not isinstance(aggregate.get("releaseGate"), str) or not aggregate["releaseGate"]:
        raise CandidateGateError("aggregate.releaseGate is required")

    coverage = aggregate.get("coverage")
    if not isinstance(coverage, dict):
        raise CandidateGateError("aggregate.coverage must be an object")
    for key in (
        "fullCanonicalCoverage",
        "fullProviderMembershipCoverage",
    ):
        _bool(coverage.get(key), f"aggregate.coverage.{key}")

    if aggregate["candidatePass"]:
        if aggregate["releaseGate"] != "REAL_PARSER_READY":
            raise CandidateGateError("passing candidate must have REAL_PARSER_READY gate")
        if not coverage["fullCanonicalCoverage"] or not coverage["fullProviderMembershipCoverage"]:
            raise CandidateGateError("passing candidate requires full real-parser coverage")


def derive_candidate_gate(
    contract: dict[str, Any],
    aggregate: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_contract(contract)
    validate_aggregate(aggregate)
    ctx = _context(context)

    regression = _bool(ctx.get("regressionDetected"), "context.regressionDetected")
    fallback = _bool(ctx.get("safeFallbackAvailable"), "context.safeFallbackAvailable")
    exhausted = _bool(ctx.get("selfRepairExhausted"), "context.selfRepairExhausted")
    current_health = ctx.get("currentRuntimeHealth")
    approval = ctx.get("approvalState")

    if aggregate["releaseGate"] in PARTIAL_GATES and not aggregate["candidatePass"] and not regression:
        decision = {
            "updateState": "CANDIDATE",
            "approvalState": "NOT_READY",
            "releaseGate": aggregate["releaseGate"],
            "nextAction": "EXPAND_COMPATIBILITY_COVERAGE",
            "ownerActionRequired": False,
            "publishEligible": False,
        }
    else:
        failure_class = "PARSER_FAILURE"
        evidence = {
            "candidatePass": aggregate["candidatePass"],
            "currentRuntimeHealth": current_health,
            "regressionDetected": regression,
            "safeFallbackAvailable": fallback,
            "selfRepairExhausted": exhausted,
            "approvalState": approval,
        }
        if not aggregate["candidatePass"]:
            evidence["failureClass"] = failure_class
        try:
            decision = evaluate_candidate(contract, evidence)
        except ContractError as exc:
            raise CandidateGateError(str(exc)) from exc

    decision["maintenanceMode"] = contract["maintenanceMode"]
    decision["candidateMode"] = contract["scope"]["candidateMode"]
    decision["evidence"] = {
        "executionMode": aggregate["executionMode"],
        "sourceReleaseGate": aggregate["releaseGate"],
        "candidatePass": aggregate["candidatePass"],
        "coverage": aggregate["coverage"],
        "repairEvidence": aggregate.get("repairEvidence", {}),
    }

    if contract["scope"]["candidateMode"] and decision.get("publishEligible"):
        raise CandidateGateError("candidateMode foundation must never become publish eligible")
    return decision


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default="compatibility/contract.json")
    parser.add_argument("--aggregate", required=True)
    parser.add_argument("--context")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        contract = load_json(args.contract)
        aggregate = load_json(args.aggregate)
        context = load_json(args.context) if args.context else None
        decision = derive_candidate_gate(contract, aggregate, context)
        rendered = json.dumps(decision, indent=2, sort_keys=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0
    except (CandidateGateError, ContractError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
