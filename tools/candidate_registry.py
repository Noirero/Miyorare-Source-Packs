#!/usr/bin/env python3
"""Build an ephemeral Compatibility Farm registry from an upstream candidate handoff.

The output is test-only input. It may move providerBaselines/currentVersion to candidate SHAs so the
real parser farm executes candidate code, but it must preserve every lastKnownGood value and never
claim approval readiness by itself.
"""
from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")
PROVIDERS = ("keiyoushi", "uma", "gekkoushi")


class CandidateRegistryError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CandidateRegistryError(f"{path} must contain a JSON object")
    return value


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value.lower()):
        raise CandidateRegistryError(f"{field} must be a 40-character git SHA")
    return value.lower()


def build_candidate_registry(base: dict[str, Any], handoff: dict[str, Any]) -> dict[str, Any]:
    if base.get("schemaVersion") != 1:
        raise CandidateRegistryError("unsupported compatibility registry schema")
    if handoff.get("schemaVersion") != 1:
        raise CandidateRegistryError("unsupported candidate handoff schema")
    if handoff.get("maintenanceMode") != "APPROVE_ONLY":
        raise CandidateRegistryError("candidate handoff must use APPROVE_ONLY")
    if handoff.get("state") != "CANDIDATE":
        raise CandidateRegistryError("candidate handoff state must be CANDIDATE")
    if handoff.get("approvalState") != "NOT_READY":
        raise CandidateRegistryError("pre-farm candidate must be NOT_READY")
    if handoff.get("publishEligible") is not False:
        raise CandidateRegistryError("pre-farm candidate cannot be publish eligible")
    if handoff.get("registryMutationAllowed") is not False:
        raise CandidateRegistryError("handoff must forbid active registry mutation")
    if handoff.get("releaseDispatchAllowed") is not False:
        raise CandidateRegistryError("handoff must forbid release dispatch")

    plan = handoff.get("plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("providers"), dict):
        raise CandidateRegistryError("candidate handoff plan.providers is required")
    validations = handoff.get("validationResults")
    if not isinstance(validations, dict):
        raise CandidateRegistryError("candidate handoff validationResults is required")
    if validations.get("integration") != "success":
        raise CandidateRegistryError("combined integration validation must succeed before real-parser handoff")

    output = deepcopy(base)
    baselines = output.get("providerBaselines")
    if not isinstance(baselines, dict):
        raise CandidateRegistryError("compatibility registry providerBaselines is required")

    candidate_providers: dict[str, dict[str, str]] = {}
    for provider in PROVIDERS:
        item = plan["providers"].get(provider)
        if not isinstance(item, dict):
            raise CandidateRegistryError(f"candidate plan is missing provider {provider}")
        current = _sha(item.get("lastKnownGood"), f"plan.providers.{provider}.lastKnownGood")
        candidate = _sha(item.get("candidate"), f"plan.providers.{provider}.candidate")
        changed = item.get("changed") is True
        validation_key = provider
        if changed:
            if validations.get(validation_key) != "success":
                raise CandidateRegistryError(f"{provider} candidate validation did not succeed")
            if provider == "gekkoushi" and validations.get("gekkoushiOverlayGuard") != "success":
                raise CandidateRegistryError("gekkoushi overlay guard did not succeed")
            baselines[provider] = candidate
            candidate_providers[provider] = {"current": current, "candidate": candidate}
        else:
            existing = _sha(baselines.get(provider), f"providerBaselines.{provider}")
            if existing != current:
                raise CandidateRegistryError(f"unchanged provider {provider} baseline does not match current LKG")

    if not candidate_providers:
        raise CandidateRegistryError("handoff contains no changed providers")

    sources = output.get("sources")
    if not isinstance(sources, list):
        raise CandidateRegistryError("compatibility registry sources must be an array")

    for source in sources:
        if not isinstance(source, dict):
            raise CandidateRegistryError("compatibility registry source entry must be an object")
        memberships = source.get("providers")
        current_versions = source.get("currentVersion")
        lkgs = source.get("lastKnownGood")
        if not isinstance(memberships, list) or not isinstance(current_versions, dict) or not isinstance(lkgs, dict):
            raise CandidateRegistryError("source provider/currentVersion/lastKnownGood metadata is incomplete")

        touched = False
        for provider, refs in candidate_providers.items():
            if provider not in memberships:
                continue
            old_lkg = _sha(lkgs.get(provider), f"{source.get('canonicalId')}.lastKnownGood.{provider}")
            if old_lkg != refs["current"]:
                raise CandidateRegistryError(
                    f"{source.get('canonicalId')} {provider} LKG does not match handoff current revision"
                )
            current_versions[provider] = refs["candidate"]
            touched = True

        if touched:
            source["updateState"] = "CANDIDATE"
            source["approvalState"] = "NOT_READY"
            source["ownerActionRequired"] = False
            source["publishEligible"] = False

    output["candidateContext"] = {
        "maintenanceMode": "APPROVE_ONLY",
        "state": "CANDIDATE",
        "approvalState": "NOT_READY",
        "providerCandidates": candidate_providers,
        "activeLastKnownGoodMutated": False,
        "publishEligible": False,
    }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = build_candidate_registry(load_json(args.registry), load_json(args.handoff))
        save_json(args.output, output)
        print(json.dumps(output["candidateContext"], indent=2, sort_keys=True))
        return 0
    except (CandidateRegistryError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
