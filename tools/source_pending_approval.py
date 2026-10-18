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


def _full_parser_pass(item: dict[str, Any]) -> bool:
    return (
        item.get("status") == "PASS"
        and item.get("parserExecution") is True
        and item.get("detailsTraversal") is True
        and item.get("chapterTraversal") is True
        and item.get("pageExtraction") is True
    )


def _held_provider_rows(
    source_providers: list[str],
    selected: set[str],
    profile_memberships: list[dict[str, Any]],
    parser_memberships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    profile_by_provider = {
        item.get("provider"): item
        for item in profile_memberships
        if isinstance(item, dict) and isinstance(item.get("provider"), str)
    }
    parser_by_provider = {
        item.get("provider"): item
        for item in parser_memberships
        if isinstance(item, dict) and isinstance(item.get("provider"), str)
    }
    held: list[dict[str, Any]] = []
    for provider in source_providers:
        if provider in selected:
            continue
        profile = profile_by_provider.get(provider, {})
        parser = parser_by_provider.get(provider, {})
        reason = profile.get("upstreamBrokenReason") or parser.get("reason")
        if not reason:
            if profile.get("profilePass") is not True:
                reason = "PROFILE_NOT_USABLE"
            elif parser and not _full_parser_pass(parser):
                reason = "REAL_PARSER_NOT_USABLE"
            else:
                reason = "PROVIDER_NOT_SELECTED"
        held.append({"provider": provider, "state": "HELD", "reason": str(reason)})
    return held


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

    source_providers = source.get("providers")
    if not isinstance(source_providers, list) or not source_providers:
        raise ValueError(f"{canonical_id} providers invalid")
    source_provider_set = set(source_providers)

    profile = evidence.get("profile")
    if not isinstance(profile, dict):
        raise ValueError(f"{canonical_id} profile evidence missing")
    profile_memberships = profile.get("memberships")
    if not isinstance(profile_memberships, list) or not profile_memberships:
        raise ValueError(f"{canonical_id} profile memberships missing")
    profile_by_provider: dict[str, dict[str, Any]] = {}
    for item in profile_memberships:
        if not isinstance(item, dict) or not isinstance(item.get("provider"), str):
            raise ValueError(f"{canonical_id} profile membership invalid")
        profile_by_provider[item["provider"]] = item
    if set(profile_by_provider) != source_provider_set:
        raise ValueError(f"{canonical_id} profile coverage does not match provider mappings")

    parser = evidence.get("parser")
    if not isinstance(parser, dict) or parser.get("gate") != "PASS":
        raise ValueError(f"{canonical_id} parser evidence is not PASS")
    parser_memberships = parser.get("memberships")
    if not isinstance(parser_memberships, list) or not parser_memberships:
        raise ValueError(f"{canonical_id} has no parser memberships")
    parser_by_provider: dict[str, dict[str, Any]] = {}
    for item in parser_memberships:
        if not isinstance(item, dict) or not isinstance(item.get("provider"), str):
            raise ValueError(f"{canonical_id} parser membership invalid")
        parser_by_provider[item["provider"]] = item
    if not set(parser_by_provider).issubset(source_provider_set):
        raise ValueError(f"{canonical_id} parser evidence contains unknown provider")

    tested = entry.get("testedVersions")
    if not isinstance(tested, dict) or not tested:
        raise ValueError(f"{canonical_id} version binding missing")
    selected = entry.get("selectedProviders")
    if selected is None:
        selected = sorted(tested)
    if not isinstance(selected, list) or not selected:
        raise ValueError(f"{canonical_id} selected provider binding missing")
    selected_set = set(selected)
    if len(selected_set) != len(selected):
        raise ValueError(f"{canonical_id} selected provider binding has duplicates")
    if not selected_set.issubset(source_provider_set):
        raise ValueError(f"{canonical_id} selected provider is not mapped")
    if set(tested) != selected_set:
        raise ValueError(f"{canonical_id} tested provider set mismatch")

    for provider in selected:
        profile_item = profile_by_provider[provider]
        if profile_item.get("profilePass") is not True:
            raise ValueError(f"{canonical_id} {provider} profile did not pass")
        parser_item = parser_by_provider.get(provider)
        if parser_item is None or not _full_parser_pass(parser_item):
            raise ValueError(f"{canonical_id} {provider} parser traversal incomplete")
        tested_sha = tested.get(provider)
        if not isinstance(tested_sha, str) or len(tested_sha) != 40:
            raise ValueError(f"{canonical_id} {provider} tested SHA invalid")
        if provider_baselines.get(provider) != tested_sha:
            raise ValueError(f"{canonical_id} {provider} provider baseline moved after test")

    held_providers = _held_provider_rows(
        source_providers,
        selected_set,
        profile_memberships,
        parser_memberships,
    )
    return {
        "canonicalId": canonical_id,
        "language": source.get("language"),
        "providers": sorted(selected_set),
        "heldProviders": held_providers,
        "testedVersions": {provider: tested[provider] for provider in sorted(selected_set)},
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
        active_providers = item["providers"]
        original_providers = list(source.get("providers", []))
        original_identities = source.get("upstreamIdentities")
        if isinstance(original_identities, dict):
            if any(provider not in original_identities for provider in active_providers):
                raise ValueError(f"{canonical_id} selected provider identity missing")
        elif set(active_providers) != set(original_providers):
            raise ValueError(f"{canonical_id} cannot narrow providers without upstream identities")

        source["authType"] = item.get("authType") or source.get("authType")
        source["adapterFamily"] = item.get("adapterFamily") or source.get("adapterFamily")
        source["providers"] = list(active_providers)
        if isinstance(original_identities, dict):
            source["upstreamIdentities"] = {
                provider: original_identities[provider]
                for provider in active_providers
            }
        source["currentVersion"] = dict(item["testedVersions"])
        source["lastKnownGood"] = dict(item["testedVersions"])
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
            "activeProviders": list(active_providers),
            "heldProviders": item["heldProviders"],
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
