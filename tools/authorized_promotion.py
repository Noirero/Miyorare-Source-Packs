#!/usr/bin/env python3
"""Fail-closed registry promotion using an exact approve-only authorization receipt.

This tool is the only promotion path intended for the approve-only lifecycle. It mutates only
provider upstreamBase/lastKnownGood after verifying an authorization receipt produced by
approval_state.authorize_promotion. It never signs, releases, or publishes.
"""
from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class AuthorizedPromotionError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuthorizedPromotionError(f"{path} must contain a JSON object")
    return value


def save_json(path: str | Path, value: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value.lower()):
        raise AuthorizedPromotionError(f"{name} must be a 40-character git SHA")
    return value.lower()


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value.lower()):
        raise AuthorizedPromotionError(f"{name} must be a SHA-256 digest")
    return value.lower()


def _validate_evidence_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise AuthorizedPromotionError("authorization evidenceBinding schemaVersion must be 1")
    count = value.get("repairEvidenceCount")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise AuthorizedPromotionError("authorization repairEvidenceCount must be a non-negative integer")
    return {
        "schemaVersion": 1,
        "farmEvidenceSha256": _digest(value.get("farmEvidenceSha256"), "authorization farmEvidenceSha256"),
        "gateSha256": _digest(value.get("gateSha256"), "authorization gateSha256"),
        "repairEvidenceSha256": _digest(value.get("repairEvidenceSha256"), "authorization repairEvidenceSha256"),
        "repairEvidenceCount": count,
    }


def validate_authorization(authorization: dict[str, Any], provider: str, commit: str) -> None:
    if authorization.get("schemaVersion") != 1:
        raise AuthorizedPromotionError("authorization schemaVersion must be 1")
    if authorization.get("authorized") is not True:
        raise AuthorizedPromotionError("promotion authorization must be explicitly authorized")
    if authorization.get("maintenanceMode") != "APPROVE_ONLY":
        raise AuthorizedPromotionError("promotion authorization must use APPROVE_ONLY")
    if authorization.get("publishEligible") is not False:
        raise AuthorizedPromotionError("promotion authorization must not be publish eligible")
    _digest(authorization.get("candidateSetId"), "authorization candidateSetId")
    _digest(authorization.get("gateFingerprint"), "authorization gateFingerprint")
    _validate_evidence_binding(authorization.get("evidenceBinding"))
    if authorization.get("provider") != provider:
        raise AuthorizedPromotionError("authorization provider does not match requested provider")
    requested = _sha(commit, "requested promotion commit")
    authorized_commit = _sha(authorization.get("commit"), "authorization commit")
    if requested != authorized_commit:
        raise AuthorizedPromotionError("requested promotion commit does not match authorization")
    approved_by = authorization.get("approvedBy")
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise AuthorizedPromotionError("authorization approvedBy is required")


def apply_authorized_promotion(
    registry: dict[str, Any],
    authorization: dict[str, Any],
    provider: str,
    commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_authorization(authorization, provider, commit)
    providers = registry.get("providers")
    if not isinstance(providers, dict):
        raise AuthorizedPromotionError("registry.providers must be an object")
    current = providers.get(provider)
    if not isinstance(current, dict):
        raise AuthorizedPromotionError(f"unknown registry provider: {provider}")

    expected = _sha(authorization.get("expectedCurrent"), "authorization expectedCurrent")
    current_lkg = _sha(current.get("lastKnownGood"), f"registry.providers.{provider}.lastKnownGood")
    if current_lkg != expected:
        raise AuthorizedPromotionError("registry lastKnownGood changed after authorization; approval is stale")

    target = _sha(commit, "requested promotion commit")
    if current_lkg == target:
        raise AuthorizedPromotionError("authorization replay rejected: candidate is already current")

    updated = deepcopy(registry)
    updated_provider = updated["providers"][provider]
    updated_provider["upstreamBase"] = target
    updated_provider["lastKnownGood"] = target

    receipt = {
        "schemaVersion": 1,
        "maintenanceMode": "APPROVE_ONLY",
        "promotionState": "PROMOTED",
        "candidateSetId": authorization["candidateSetId"],
        "provider": provider,
        "previousLastKnownGood": expected,
        "commit": target,
        "approvedBy": authorization["approvedBy"],
        "gateFingerprint": authorization["gateFingerprint"],
        "evidenceBinding": deepcopy(authorization["evidenceBinding"]),
        "publishEligible": False,
    }
    return updated, receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        updated, receipt = apply_authorized_promotion(
            load_json(args.registry),
            load_json(args.authorization),
            args.provider,
            args.commit.lower(),
        )
        save_json(args.registry, updated)
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        save_json(args.receipt, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except (AuthorizedPromotionError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
