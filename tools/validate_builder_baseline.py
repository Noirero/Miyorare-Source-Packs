#!/usr/bin/env python3
"""Validate the pinned Miyorare builder baseline used for stable Source Pack builds."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")


class BaselineError(ValueError):
    pass


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"could not read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BaselineError(f"{path} must contain a JSON object")
    return value


def validate(baseline: dict[str, Any], contract: dict[str, Any]) -> str:
    if baseline.get("schemaVersion") != 1:
        raise BaselineError("unsupported builder baseline schema")
    if baseline.get("repository") != "Noirero/Miyorare":
        raise BaselineError("builder repository must be Noirero/Miyorare")
    if baseline.get("lineageBranch") != "beta":
        raise BaselineError("builder lineage branch must remain beta")
    commit = baseline.get("builderCommit")
    if not isinstance(commit, str) or not HEX40.fullmatch(commit.lower()):
        raise BaselineError("builderCommit must be an exact 40-character git SHA")

    consumer = contract.get("consumer") or {}
    compatibility = contract.get("compatibility") or {}
    if consumer.get("builderResolution") != "pinned-commit":
        raise BaselineError("contract must require pinned-commit builder resolution")
    if consumer.get("builderBaselineFile") != "compatibility/miyorare-builder-baseline.json":
        raise BaselineError("contract builder baseline path mismatch")
    if compatibility.get("movingBetaAsStableAuthority") != "reject":
        raise BaselineError("contract must reject moving beta as stable authority")
    if baseline.get("compatibilityEpoch") != compatibility.get("compatibilityEpoch"):
        raise BaselineError("builder baseline compatibility epoch mismatch")
    if baseline.get("tsukiApi") != compatibility.get("tsukiApi"):
        raise BaselineError("builder baseline Tsuki API mismatch")

    policy = baseline.get("policy")
    if not isinstance(policy, dict):
        raise BaselineError("builder baseline policy is required")
    if policy.get("movingBranchResolutionAllowedForStableRelease") is not False:
        raise BaselineError("stable release must not resolve a moving builder branch")
    if policy.get("stableRuntimeBaselineBranch") != "main":
        raise BaselineError("stable runtime baseline branch must be main")
    return commit.lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--print-commit", action="store_true")
    args = parser.parse_args()
    try:
        commit = validate(load_object(args.baseline), load_object(args.contract))
    except BaselineError as exc:
        print(f"error: {exc}")
        return 1
    if args.print_commit:
        print(commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
