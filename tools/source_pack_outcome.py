#!/usr/bin/env python3
"""Classify Source Pack domain state as PASS, HELD, or FAIL.

PASS: active last-known-good set is valid and no candidate is being held.
HELD: active last-known-good set remains safe, but one or more candidate updates are blocked.
FAIL: state is malformed, unknown, or reports an active broken condition.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PASS_STATES = {"synced", "promoted"}
HELD_STATES = {"held", "promoted-with-held-sources", "waiting-approval"}
FAIL_STATES = {"broken", "failed", "unknown"}


def classify(status: dict[str, Any]) -> dict[str, Any]:
    providers = status.get("providers")
    if status.get("schema") not in (2, 3) or not isinstance(providers, dict) or not providers:
        return {
            "schemaVersion": 1,
            "outcome": "FAIL",
            "activeSetSafe": False,
            "reason": "invalid-status-schema",
            "providers": {},
        }

    normalized: dict[str, str] = {}
    held: list[str] = []
    failed: list[str] = []
    for name, info in sorted(providers.items()):
        state = info.get("state") if isinstance(info, dict) else None
        state = str(state or "unknown")
        normalized[name] = state
        if state in HELD_STATES:
            held.append(name)
        elif state in FAIL_STATES or state not in PASS_STATES:
            failed.append(name)

    if failed:
        outcome = "FAIL"
        safe = False
        reason = "active-or-status-failure"
    elif held:
        outcome = "HELD"
        safe = True
        reason = "candidate-update-held-last-known-good-active"
    else:
        outcome = "PASS"
        safe = True
        reason = "all-providers-pass"

    return {
        "schemaVersion": 1,
        "outcome": outcome,
        "activeSetSafe": safe,
        "reason": reason,
        "workflowRunId": status.get("workflowRunId"),
        "providers": normalized,
        "heldProviders": held,
        "failedProviders": failed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    status = json.loads(args.status.read_text(encoding="utf-8"))
    result = classify(status)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 1 if result["outcome"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
