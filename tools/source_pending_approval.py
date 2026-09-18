#!/usr/bin/env python3
"""Fail-closed one-click approval for autonomous PENDING source onboarding."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

READY = "READY_FOR_APPROVAL"
APPROVED = "APPROVED"
REAL_PASS = "REAL_PARSER_PASS"


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = registry.get("sources")
    if not isinstance(rows, list):
        raise ValueError("registry.sources must be a list")
    result: dict[str, dict[str, Any]] = {}
    for source in rows:
        canonical_id = source.get("canonicalId") if isinstance(source, dict) else None
        if not isinstance(canonical_id, str) or not canonical_id:
            raise ValueError("registry source missing canonicalId")
        if canonical_id in result:
            raise ValueError(f"duplicate canonicalId: {canonical_id}")
        result[canonical_id] = source
    return result


def validate_ready_source(
    source: dict[str, Any],
    entry: dict[str, Any],
    provider_baselines: dict[str, Any],
) -> dict[str, Any]:
    canonical_id = source["canonicalId"]
    enrollment = source.get("compatibilityEnrollment", {})
    if enrollment.get("state") != "PENDING":
        raise ValueError(f"{canonical_id} is not PENDING")
    if entry.get("schemaVersion") != 2:
        raise ValueError(f"{canonical_id} worker evidence is not schema v2")
    if entry.get("state") != READY or entry.get("approvalState") != "WAITING_FOR_APPROVAL":
        raise ValueError(f"{canonical_id} is not waiting for onboarding approval")

    evidence = entry.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError(f"{canonical_id} evidence missing")
    if entry.get("evidenceSha256") != digest(evidence):
        raise ValueError(f"{canonical_id} evidence digest mismatch")
    if evidence.get("gate") != REAL_PASS:
        raise ValueError(f"{canonical_id} did not pass real-parser gate")

    parser = evidence.get("parser")
    if not isinstance(parser, dict) or parser.get("gate") != "PASS":
        raise ValueError(f"{canonical_id} parser evidence is not PASS")
    memberships = parser.get("memberships")
    if not isinstance(memberships, list) or not memberships:
        raise ValueError(f"{canonical_id} has no parser memberships")

    providers = source.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ValueError(f"{canonical_id} providers invalid")
    by_provider: dict[str, dict[str, Any]] = {}
    for item in memberships:
        if not isinstance(item, dict) or not isinstance(item.get("provider"), str):
            raise ValueError(f"{canonical_id} parser membership invalid")
        by_provider[item["provider"]] = item
    if set(by_provider) != set(providers):
        raise ValueError(f"{canonical_id} parser coverage does not match provider mappings")

    for provider in providers:
        item = by_provider[provider]
        passed = (
            item.get("status") == "PASS"
            and item.get("parserExecution") is True
            and item.get("detailsTraversal") is True
            and item.get("chapterTraversal") is True
            and item.get("pageExtraction") is True
        )
        if not passed:
            raise ValueError(f"{canonical_id} {provider} parser traversal incomplete")

    tested = entry.get("testedVersions")
    current = source.get("currentVersion")
    if not isinstance(tested, dict) or not isinstance(current, dict):
        raise ValueError(f"{canonical_id} version binding missing")
    if set(tested) != set(providers):
        raise ValueError(f"{canonical_id} tested provider set mismatch")
    for provider in providers:
        tested_sha = tested.get(provider)
        if not isinstance(tested_sha, str) or len(tested_sha) != 40:
            raise ValueError(f"{canonical_id} {provider} tested SHA invalid")
        if current.get(provider) != tested_sha:
            raise ValueError(f"{canonical_id} {provider} source version moved after test")
        if provider_baselines.get(provider) != tested_sha:
            raise ValueError(f"{canonical_id} {provider} provider baseline moved after test")

    return {
        "canonicalId": canonical_id,
        "language": source.get("language"),
        "providers": sorted(providers),
        "testedVersions": {provider: tested[provider] for provider in sorted(providers)},
        "workerRunId": str(entry.get("workflowRunId", "")),
        "evidenceSha256": entry["evidenceSha256"],
        "adapterFamily": entry.get("adapterFamily"),
        "authType": entry.get("authType"),
    }


def plan(registry: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    if state.get("schemaVersion") != 2:
        raise ValueError("pending worker state must be schema v2")
    sources = source_map(registry)
    provider_baselines = registry.get("providerBaselines")
    if not isinstance(provider_baselines, dict):
        raise ValueError("registry.providerBaselines invalid")

    candidates: list[dict[str, Any]] = []
    for canonical_id, entry in sorted(state.get("sources", {}).items()):
        if not isinstance(entry, dict) or entry.get("state") != READY:
            continue
        source = sources.get(canonical_id)
        if source is None:
            raise ValueError(f"worker READY source missing from registry: {canonical_id}")
        candidates.append(validate_ready_source(source, entry, provider_baselines))

    return {
        "schemaVersion": 1,
        "action": "APPROVE_READY_SOURCES",
        "count": len(candidates),
        "sources": candidates,
    }


def apply(
    registry: dict[str, Any],
    state: dict[str, Any],
    approval_plan: dict[str, Any],
    approved_by: str,
    approved_at: str,
    approval_run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    live_plan = plan(registry, state)
    if live_plan != approval_plan:
        raise ValueError("approval plan changed; refusing stale approval")
    if live_plan.get("count", 0) < 1:
        raise ValueError("no READY_FOR_APPROVAL sources exist")

    sources = source_map(registry)
    state_sources = state.get("sources", {})
    approved: list[dict[str, Any]] = []

    for item in live_plan["sources"]:
        canonical_id = item["canonicalId"]
        source = sources[canonical_id]
        entry = state_sources[canonical_id]

        source["authType"] = item.get("authType") or source.get("authType")
        source["adapterFamily"] = item.get("adapterFamily") or source.get("adapterFamily")
        source["compatibilityEnrollment"] = {
            "state": "ACTIVE",
            "parserCoverageRequired": True,
        }
        source["runtimeHealth"] = "HEALTHY"
        source["ownerActionRequired"] = False
        source["publishEligible"] = False
        reasons = source.setdefault("selectionReasons", [])
        if "autonomous-real-parser-approved" not in reasons:
            reasons.append("autonomous-real-parser-approved")
        history = source.setdefault("healthyHistory", [])
        for commit in item["testedVersions"].values():
            if commit not in history:
                history.append(commit)
        source["onboardingApproval"] = {
            "schemaVersion": 1,
            "state": APPROVED,
            "approvedBy": approved_by,
            "approvedAt": approved_at,
            "approvalRunId": str(approval_run_id),
            "workerRunId": item["workerRunId"],
            "evidenceSha256": item["evidenceSha256"],
            "testedVersions": item["testedVersions"],
        }

        entry["state"] = APPROVED
        entry["approvalState"] = APPROVED
        entry["approvedBy"] = approved_by
        entry["approvedAt"] = approved_at
        entry["approvalRunId"] = str(approval_run_id)
        entry["publishEligible"] = False

        approved.append(item)

    state["updatedAt"] = approved_at
    receipt = {
        "schemaVersion": 1,
        "action": "APPROVE_READY_SOURCES",
        "state": APPROVED,
        "approvalRunId": str(approval_run_id),
        "approvedBy": approved_by,
        "approvedAt": approved_at,
        "count": len(approved),
        "sources": approved,
        "publishEligible": False,
    }
    summary = {
        "schemaVersion": 1,
        "approved": len(approved),
        "canonicalIds": [item["canonicalId"] for item in approved],
    }
    return registry, state, receipt | {"summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan")
    p.add_argument("--registry", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--output", required=True)

    a = sub.add_parser("apply")
    a.add_argument("--registry", required=True)
    a.add_argument("--state", required=True)
    a.add_argument("--plan", required=True)
    a.add_argument("--approved-by", required=True)
    a.add_argument("--approved-at", required=True)
    a.add_argument("--approval-run-id", required=True)
    a.add_argument("--receipt", required=True)

    args = parser.parse_args()
    if args.command == "plan":
        save(args.output, plan(load(args.registry), load(args.state)))
        return 0

    registry = load(args.registry)
    state = load(args.state)
    updated_registry, updated_state, receipt = apply(
        registry,
        state,
        load(args.plan),
        args.approved_by,
        args.approved_at,
        args.approval_run_id,
    )
    save(args.registry, updated_registry)
    save(args.state, updated_state)
    save(args.receipt, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
