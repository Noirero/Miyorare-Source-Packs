#!/usr/bin/env python3
"""Machine-readable safety contract for the Miyorare Compatibility Farm.

This module deliberately contains no provider/source-specific logic. Provider adapters
produce evidence; this evaluator turns that evidence into an update/release decision.
The central invariant is that HELD/UNKNOWN is a safety state, not an assignment for the
repository owner to edit source code manually.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_LANGUAGES = {"id", "en"}
REQUIRED_PROVIDERS = {"keiyoushi", "uma", "gekkoushi"}
REQUIRED_CAPABILITIES = {
    "load",
    "browse",
    "search",
    "details",
    "chapters",
    "content",
    "authenticate",
    "download",
    "reader",
}
REQUIRED_AUTH_TYPES = {
    "NO_AUTH",
    "COOKIE",
    "FORM",
    "WEBVIEW",
    "TOKEN",
    "INTERACTIVE_REQUIRED",
    "UNSUPPORTED",
}
REQUIRED_FAILURE_CLASSES = {
    "MIYORARE_REGRESSION",
    "UPSTREAM_CHANGED",
    "SOURCE_DOWN",
    "AUTH_REQUIRED",
    "RATE_LIMITED",
    "NETWORK_FAILURE",
    "PARSER_FAILURE",
    "CONTENT_FAILURE",
    "DOWNLOAD_FAILURE",
    "READER_FAILURE",
    "UNKNOWN",
}
REQUIRED_UPDATE_STATES = {"CANDIDATE", "PROMOTED", "HELD"}
REQUIRED_RUNTIME_STATES = {"HEALTHY", "DEGRADED", "BROKEN", "UNKNOWN"}
REQUIRED_APPROVAL_STATES = {
    "NOT_READY",
    "WAITING_FOR_APPROVAL",
    "APPROVED",
    "REJECTED",
}
REQUIRED_MANGA_STEPS = {
    "chapter",
    "page_list",
    "image_fetch",
    "decode",
    "download",
    "reader",
}
REQUIRED_NOVEL_STEPS = {
    "chapter",
    "html_or_text",
    "parsing",
    "formatting",
    "offline_if_supported",
    "novel_reader",
}


class ContractError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require_exact_set(document: dict[str, Any], key: str, expected: set[str]) -> None:
    actual = document.get(key)
    if not isinstance(actual, list) or set(actual) != expected or len(actual) != len(expected):
        raise ContractError(f"{key} must contain exactly: {sorted(expected)}")


def _require_true(policy: dict[str, Any], key: str) -> None:
    if policy.get(key) is not True:
        raise ContractError(f"policies.{key} must be true")


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schemaVersion") != 1:
        raise ContractError("schemaVersion must be 1")
    if contract.get("maintenanceMode") != "APPROVE_ONLY":
        raise ContractError("maintenanceMode must be APPROVE_ONLY")

    scope = contract.get("scope")
    if not isinstance(scope, dict):
        raise ContractError("scope must be an object")
    _require_exact_set(scope, "languages", REQUIRED_LANGUAGES)
    _require_exact_set(scope, "providers", REQUIRED_PROVIDERS)
    if scope.get("candidateMode") is not True:
        raise ContractError("scope.candidateMode must initially be true")

    _require_exact_set(contract, "capabilities", REQUIRED_CAPABILITIES)
    _require_exact_set(contract, "authenticationTypes", REQUIRED_AUTH_TYPES)
    _require_exact_set(contract, "failureClasses", REQUIRED_FAILURE_CLASSES)
    _require_exact_set(contract, "updateStates", REQUIRED_UPDATE_STATES)
    _require_exact_set(contract, "runtimeHealthStates", REQUIRED_RUNTIME_STATES)
    _require_exact_set(contract, "approvalStates", REQUIRED_APPROVAL_STATES)

    profiles = contract.get("contentProfiles")
    if not isinstance(profiles, dict):
        raise ContractError("contentProfiles must be an object")
    _require_exact_set(profiles, "manga", REQUIRED_MANGA_STEPS)
    _require_exact_set(profiles, "novel", REQUIRED_NOVEL_STEPS)

    policy = contract.get("policies")
    if not isinstance(policy, dict):
        raise ContractError("policies must be an object")
    for key in (
        "unknownTriggersAutoDiagnose",
        "safeSelfRepairBeforeHold",
        "keepLastKnownGood",
        "maintainHealthyHistory",
        "validatedCanonicalFallback",
        "protectMiyorareCustomization",
        "publishRequiresApproval",
        "candidateFailureDoesNotImplyCurrentBroken",
    ):
        _require_true(policy, key)
    if policy.get("holdRequiresOwnerAction") is not False:
        raise ContractError("policies.holdRequiresOwnerAction must be false")
    if policy.get("publishFromCandidateMode") is not False:
        raise ContractError("policies.publishFromCandidateMode must be false during dry-run foundation")
    if policy.get("regressionBudget") != 0:
        raise ContractError("policies.regressionBudget must be 0")


def _base_decision() -> dict[str, Any]:
    return {
        "updateState": "HELD",
        "approvalState": "NOT_READY",
        "releaseGate": "NOT_READY",
        "nextAction": "AUTO_DIAGNOSE",
        "ownerActionRequired": False,
        "publishEligible": False,
    }


def evaluate_candidate(contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Evaluate candidate evidence without mutating registry/runtime state.

    Expected evidence fields are intentionally provider-neutral:
      candidatePass: bool
      currentRuntimeHealth: HEALTHY|DEGRADED|BROKEN|UNKNOWN
      failureClass: optional failure class when candidatePass is false
      regressionDetected: bool
      safeFallbackAvailable: bool
      selfRepairExhausted: bool
      approvalState: optional NOT_READY|WAITING_FOR_APPROVAL|APPROVED|REJECTED

    Provider/family adapters are responsible for creating the underlying evidence.
    """
    validate_contract(contract)
    decision = _base_decision()

    candidate_pass = evidence.get("candidatePass")
    if not isinstance(candidate_pass, bool):
        raise ContractError("evidence.candidatePass must be boolean")

    current_health = evidence.get("currentRuntimeHealth")
    if current_health not in REQUIRED_RUNTIME_STATES:
        raise ContractError("evidence.currentRuntimeHealth is invalid")

    regression = evidence.get("regressionDetected", False)
    if not isinstance(regression, bool):
        raise ContractError("evidence.regressionDetected must be boolean")

    approval = evidence.get("approvalState", "NOT_READY")
    if approval not in REQUIRED_APPROVAL_STATES:
        raise ContractError("evidence.approvalState is invalid")

    if regression:
        decision.update(
            releaseGate="BLOCKED_REGRESSION",
            nextAction="AUTO_DIAGNOSE",
            failureClass="MIYORARE_REGRESSION",
        )
        return decision

    if candidate_pass:
        if approval == "REJECTED":
            decision.update(releaseGate="REJECTED", nextAction="KEEP_CURRENT")
            return decision

        if approval == "APPROVED":
            decision.update(
                updateState="CANDIDATE",
                approvalState="APPROVED",
                releaseGate="APPROVED_DRY_RUN",
                nextAction="KEEP_CANDIDATE_READY",
            )
            # Initial foundation intentionally cannot publish. A later, separately
            # reviewed phase will turn candidate mode off and wire sign/publish.
            decision["publishEligible"] = not contract["scope"]["candidateMode"]
            return decision

        decision.update(
            updateState="CANDIDATE",
            approvalState="WAITING_FOR_APPROVAL",
            releaseGate="WAITING_FOR_APPROVAL",
            nextAction="WAIT_FOR_APPROVAL",
        )
        return decision

    failure_class = evidence.get("failureClass", "UNKNOWN")
    if failure_class not in REQUIRED_FAILURE_CLASSES:
        raise ContractError("evidence.failureClass is invalid")
    decision["failureClass"] = failure_class

    exhausted = evidence.get("selfRepairExhausted", False)
    fallback = evidence.get("safeFallbackAvailable", False)
    if not isinstance(exhausted, bool) or not isinstance(fallback, bool):
        raise ContractError("selfRepairExhausted and safeFallbackAvailable must be boolean")

    if not exhausted:
        decision["nextAction"] = (
            "AUTO_DIAGNOSE" if failure_class == "UNKNOWN" else "AUTO_REPAIR_OR_DIAGNOSE"
        )
        return decision

    if current_health in {"HEALTHY", "DEGRADED"}:
        decision.update(releaseGate="AUTO_HOLD", nextAction="KEEP_CURRENT")
        return decision

    if fallback:
        decision.update(releaseGate="AUTO_HOLD", nextAction="RECOVER_HEALTHY_VERSION")
        return decision

    # Only after safe repair has been exhausted AND the active version has no safe
    # fallback does this become exceptional engineering work.
    if current_health == "BROKEN":
        decision.update(
            releaseGate="TEMPORARILY_UNAVAILABLE",
            nextAction="ENGINEERING_ESCALATION_REQUIRED",
            ownerActionRequired=True,
        )
        return decision

    decision.update(releaseGate="AUTO_HOLD", nextAction="KEEP_CURRENT_OR_RECHECK")
    return decision


def _command_validate(args: argparse.Namespace) -> int:
    validate_contract(load_json(args.contract))
    print("compatibility contract: valid")
    return 0


def _command_evaluate(args: argparse.Namespace) -> int:
    contract = load_json(args.contract)
    evidence = load_json(args.evidence)
    print(json.dumps(evaluate_candidate(contract, evidence), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate a Compatibility Farm contract")
    validate.add_argument("--contract", default="compatibility/contract.json")
    validate.set_defaults(func=_command_validate)

    evaluate = sub.add_parser("evaluate", help="evaluate provider-neutral candidate evidence")
    evaluate.add_argument("--contract", default="compatibility/contract.json")
    evaluate.add_argument("--evidence", required=True)
    evaluate.set_defaults(func=_command_evaluate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
