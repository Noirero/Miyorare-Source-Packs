#!/usr/bin/env python3
"""Validate the exact cross-repository baseline for the Hiraukan audio catalog.

This contract is intentionally independent from the Miyorare manga builder baseline.
A draft/blocked baseline may be structurally valid, but production callers must use
--require-release-eligible before publishing the audio catalog.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")
KIND = "MIYORARE_AUDIO_CATALOG_BASELINE"
EXPECTED_RUNTIME_IDS = {
    "miyorare.audio.asmr_one",
    "miyorare.audio.hentai_asmr",
    "miyorare.audio.japanese_asmr",
    "miyorare.audio.asmr18",
    "miyorare.audio.ero_voice",
    "miyorare.audio.asmr_hentai_net",
}


class BaselineError(ValueError):
    pass


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BaselineError(f"{name} must be an object")
    return value


def _exact_sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or HEX40.fullmatch(value) is None:
        raise BaselineError(f"{name} must be an exact lowercase 40-character SHA")
    return value


def validate_data(data: dict[str, Any], *, require_release_eligible: bool = False) -> dict[str, Any]:
    if data.get("schemaVersion") != 1 or data.get("kind") != KIND:
        raise BaselineError("unsupported audio catalog baseline schema/kind")

    miyorare = _mapping(data.get("miyorare"), "miyorare")
    if miyorare.get("repository") != "Noirero/Miyorare":
        raise BaselineError("miyorare.repository must be Noirero/Miyorare")
    if miyorare.get("lineageBranch") != "beta":
        raise BaselineError("miyorare.lineageBranch must be beta")
    miyorare_commit = _exact_sha(miyorare.get("catalogCommit"), "miyorare.catalogCommit")
    if miyorare.get("catalogPath") != "extensions/miyorare-audio/pack.json":
        raise BaselineError("unexpected Miyorare audio catalog path")
    if miyorare.get("validatorPath") != "extensions/miyorare-audio/tools/validate_pack.py":
        raise BaselineError("unexpected Miyorare audio catalog validator path")
    source_pr = miyorare.get("sourcePullRequest")
    if not isinstance(source_pr, int) or source_pr < 1:
        raise BaselineError("miyorare.sourcePullRequest must be a positive integer")

    hiraukan = _mapping(data.get("hiraukan"), "hiraukan")
    if hiraukan.get("repository") != "Noirero/Hiraukan":
        raise BaselineError("hiraukan.repository must be Noirero/Hiraukan")
    if hiraukan.get("lineageBranch") != "beta":
        raise BaselineError("hiraukan.lineageBranch must be beta")
    hiraukan_commit = _exact_sha(hiraukan.get("runtimeCommit"), "hiraukan.runtimeCommit")
    if hiraukan.get("runtimeRegistryPath") != "lib/src/extensions/audio_extension_provider.dart":
        raise BaselineError("unexpected Hiraukan audio runtime registry path")

    runtime_ids = data.get("expectedRuntimeIds")
    if not isinstance(runtime_ids, list) or not all(isinstance(item, str) for item in runtime_ids):
        raise BaselineError("expectedRuntimeIds must be a string list")
    if len(runtime_ids) != len(set(runtime_ids)):
        raise BaselineError("expectedRuntimeIds contains duplicates")
    if set(runtime_ids) != EXPECTED_RUNTIME_IDS:
        raise BaselineError("expectedRuntimeIds does not match the six Hiraukan audio runtimes")

    eligibility = _mapping(data.get("releaseEligibility"), "releaseEligibility")
    state = eligibility.get("state")
    device_validated = eligibility.get("realDeviceValidated")
    beta_merged = eligibility.get("miyorareBetaMerged")
    reason = eligibility.get("reason")
    if state not in {"BLOCKED", "ELIGIBLE"}:
        raise BaselineError("releaseEligibility.state must be BLOCKED or ELIGIBLE")
    if not isinstance(device_validated, bool) or not isinstance(beta_merged, bool):
        raise BaselineError("release eligibility evidence flags must be boolean")
    if not isinstance(reason, str) or not reason.strip():
        raise BaselineError("releaseEligibility.reason is required")
    if state == "ELIGIBLE" and not (device_validated and beta_merged):
        raise BaselineError("ELIGIBLE requires real-device validation and final Miyorare beta merge")
    if state == "BLOCKED" and device_validated and beta_merged:
        raise BaselineError("BLOCKED cannot retain both promotion gates as satisfied")
    if require_release_eligible and state != "ELIGIBLE":
        raise BaselineError(f"audio catalog release remains blocked: {reason}")

    return {
        "miyorareCommit": miyorare_commit,
        "hiraukanCommit": hiraukan_commit,
        "releaseEligibility": state,
        "releaseEligibilityReason": reason,
    }


def validate(path: Path, *, require_release_eligible: bool = False) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BaselineError("baseline root must be an object")
    return validate_data(data, require_release_eligible=require_release_eligible)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--require-release-eligible", action="store_true")
    parser.add_argument("--print-miyorare-commit", action="store_true")
    parser.add_argument("--print-hiraukan-commit", action="store_true")
    args = parser.parse_args()

    result = validate(args.baseline, require_release_eligible=args.require_release_eligible)
    if args.print_miyorare_commit:
        print(result["miyorareCommit"])
    elif args.print_hiraukan_commit:
        print(result["hiraukanCommit"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
