#!/usr/bin/env python3
"""Stage approve-only upstream candidates into runtime status without moving active/LKG state.

The lifecycle deliberately keeps candidate state separate from active runtime health. Staging a
passing candidate sets updateState=CANDIDATE and WAITING_FOR_APPROVAL metadata while preserving
activeCommit, lastKnownGood, healthyHistory, runtimeHealth, and recovery state.
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from approval_state import ApprovalStateError, load_json as load_approval_json, validate_pending


class CandidateLifecycleError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CandidateLifecycleError(f"{path} must contain a JSON object")
    return value


def save_json(path: str | Path, value: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def stage_waiting(status: dict[str, Any], pending: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_pending(pending)
    except ApprovalStateError as exc:
        raise CandidateLifecycleError(str(exc)) from exc

    if status.get("schema") != 3:
        raise CandidateLifecycleError("upstream status schema must be 3")
    providers = status.get("providers")
    if not isinstance(providers, dict):
        raise CandidateLifecycleError("status.providers must be an object")

    updated = deepcopy(status)
    for provider, candidate in pending["providers"].items():
        state = updated["providers"].get(provider)
        if not isinstance(state, dict):
            raise CandidateLifecycleError(f"status is missing provider {provider}")

        current_lkg = state.get("lastKnownGood")
        if current_lkg != candidate["current"]:
            raise CandidateLifecycleError(f"{provider} status lastKnownGood changed; pending candidate is stale")
        if state.get("activeCommit") != candidate["current"]:
            raise CandidateLifecycleError(f"{provider} activeCommit does not match staged current revision")

        state["updateState"] = "CANDIDATE"
        state["candidate"] = {
            "commit": candidate["candidate"],
            "expectedLastKnownGood": candidate["current"],
            "candidateSetId": pending["candidateSetId"],
            "approvalState": "WAITING_FOR_APPROVAL",
            "publishEligible": False,
        }
        state["reason"] = "waiting-for-exact-approval"

    return updated


def hold_candidate(
    status: dict[str, Any],
    provider: str,
    candidate_commit: str,
    reason: str,
) -> dict[str, Any]:
    if status.get("schema") != 3:
        raise CandidateLifecycleError("upstream status schema must be 3")
    updated = deepcopy(status)
    state = updated.get("providers", {}).get(provider)
    if not isinstance(state, dict):
        raise CandidateLifecycleError(f"status is missing provider {provider}")
    active = state.get("activeCommit")
    lkg = state.get("lastKnownGood")
    runtime = state.get("runtimeHealth")
    state["updateState"] = "HELD"
    state["candidate"] = {
        "commit": candidate_commit,
        "approvalState": "NOT_READY",
        "publishEligible": False,
        "reason": reason,
    }
    state["reason"] = reason
    if state.get("activeCommit") != active or state.get("lastKnownGood") != lkg or state.get("runtimeHealth") != runtime:
        raise CandidateLifecycleError("holding a candidate must not mutate active runtime state")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage")
    stage.add_argument("--status", required=True, type=Path)
    stage.add_argument("--pending", required=True, type=Path)
    hold = sub.add_parser("hold")
    hold.add_argument("--status", required=True, type=Path)
    hold.add_argument("--provider", required=True)
    hold.add_argument("--candidate", required=True)
    hold.add_argument("--reason", required=True)
    args = parser.parse_args()

    try:
        status = load_json(args.status)
        if args.command == "stage":
            updated = stage_waiting(status, load_approval_json(args.pending))
        else:
            updated = hold_candidate(status, args.provider, args.candidate, args.reason)
        save_json(args.status, updated)
        print(json.dumps(updated, indent=2, sort_keys=True))
        return 0
    except (CandidateLifecycleError, ApprovalStateError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
