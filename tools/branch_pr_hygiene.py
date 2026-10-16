#!/usr/bin/env python3
"""Evaluate branch/PR cleanup eligibility without deleting anything."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

STATE_BEARING = {"main", "compatibility-farm-foundation"}
ACTIVE_PREFIXES = ("feat/", "fix/", "hardening/", "audit/", "phase", "perf/")
EPHEMERAL_PREFIXES = ("cleanup-", "cleanup/", "dispatch-")
EPHEMERAL_MARKERS = ("compatibility-snapshot-", "release-eligibility-")


def classify(branch: str) -> str:
    if branch in STATE_BEARING:
        return "STATE_BEARING"
    if branch.startswith(ACTIVE_PREFIXES):
        return "ACTIVE_WORK"
    if branch.startswith(EPHEMERAL_PREFIXES) or any(marker in branch for marker in EPHEMERAL_MARKERS):
        return "EPHEMERAL"
    return "UNKNOWN"


def evaluate(record: dict[str, Any]) -> dict[str, str]:
    branch = record.get("branch")
    if not isinstance(branch, str) or not branch:
        raise ValueError("branch is required")
    observed = classify(branch)
    declared = record.get("classification", observed)
    if declared != observed:
        return {"branch": branch, "classification": observed, "decision": "HELD", "reason": "classification-mismatch"}
    if observed == "STATE_BEARING":
        return {"branch": branch, "classification": observed, "decision": "PROTECTED", "reason": "state-bearing"}
    if observed == "UNKNOWN":
        return {"branch": branch, "classification": observed, "decision": "HELD", "reason": "unknown-classification"}
    if record.get("openPullRequest") is True:
        return {"branch": branch, "classification": observed, "decision": "HELD", "reason": "open-pull-request"}
    refs = record.get("activeReferences")
    if not isinstance(refs, list):
        return {"branch": branch, "classification": observed, "decision": "HELD", "reason": "missing-reference-scan"}
    if refs:
        return {"branch": branch, "classification": observed, "decision": "HELD", "reason": "active-reference"}
    pr_state = record.get("pullRequestState")
    if pr_state == "MERGED":
        if record.get("liveTargetVerified") is not True:
            return {"branch": branch, "classification": observed, "decision": "HELD", "reason": "merge-not-post-verified"}
        return {"branch": branch, "classification": observed, "decision": "CLEANUP_ELIGIBLE", "reason": "merged-and-post-verified"}
    if pr_state == "CLOSED_UNMERGED":
        if record.get("abandonmentApproved") is not True:
            return {"branch": branch, "classification": observed, "decision": "HELD", "reason": "unmerged-not-approved-abandoned"}
        return {"branch": branch, "classification": observed, "decision": "CLEANUP_ELIGIBLE", "reason": "approved-abandonment"}
    if observed == "EPHEMERAL" and record.get("purposeComplete") is True and record.get("purposeEvidence"):
        return {"branch": branch, "classification": observed, "decision": "CLEANUP_ELIGIBLE", "reason": "ephemeral-purpose-complete"}
    return {"branch": branch, "classification": observed, "decision": "HELD", "reason": "insufficient-evidence"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("input must be a JSON array")
    result = [evaluate(item) for item in data]
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
