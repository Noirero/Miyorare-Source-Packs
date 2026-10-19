#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

PRIMARY = ("uma", "gekkoushi")
RUNTIME_DECISIONS = {
    "B3_VALIDATE_PRIMARY_BEFORE_IGNORING_REFERENCE_GAP",
    "B3_TARGETED_PRIMARY_DISCOVERY_VALIDATION",
    "B3_RECONCILE_MISSING_PRIMARY_WITH_HEALTHY_FALLBACK",
    "B3_RECONCILE_DISCOVERY_WITH_HEALTHY_PRIMARY_LKG",
    "B3_TARGETED_REPAIR_AND_DISCOVERY_VALIDATION",
    "B3_CONFIRM_UNAVAILABLE_OR_REPLACEMENT",
    "B3_RUNTIME_AND_DISCOVERY_VALIDATION_REQUIRED",
    "B3_TARGETED_IDENTITY_INVESTIGATION",
    "B3_PRIMARY_COVERAGE_DISCOVERY_REQUIRED",
}
NO_RUNTIME_DECISION = "B3_PRIMARY_COVERAGE_DECISION_REQUIRED"


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def index_inventory(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = value.get("sources")
    if not isinstance(rows, list):
        raise ValueError("inventory.sources must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("language") != "en":
            continue
        cid = row.get("canonicalId")
        if isinstance(cid, str):
            if cid in result:
                raise ValueError(f"duplicate inventory canonicalId: {cid}")
            result[cid] = row
    return result


def _identity(provider: str, mapping: Any) -> tuple[Any, ...] | None:
    if not isinstance(mapping, dict):
        return None
    if provider == "keiyoushi":
        return (mapping.get("module"), str(mapping.get("sourceId") or ""), mapping.get("sourceName"))
    return (mapping.get("file"), mapping.get("sourceName"))


def validate_b2(b2: dict[str, Any]) -> list[dict[str, Any]]:
    if b2.get("phase") != "TRACK_B_BATCH_2_CAPABILITY_HEALTH_DECISION":
        raise ValueError("B3 requires Track B Batch 2 report")
    if b2.get("readOnly") is not True or b2.get("status") != "COMPLETE_WITH_DECISIONS":
        raise ValueError("B3 requires completed read-only B2 report")
    rows = [
        row for row in b2.get("decisions", [])
        if isinstance(row, dict) and row.get("decision", {}).get("nextPhase") == "TRACK_B_BATCH_3"
    ]
    expected = b2.get("summary", {}).get("batch3Rows")
    if expected != 33 or len(rows) != 33:
        raise ValueError(f"B3 requires exact 33-row B2 cohort, got expected={expected} actual={len(rows)}")
    ids = [row.get("canonicalId") for row in rows]
    if any(not isinstance(cid, str) for cid in ids) or len(set(ids)) != len(ids):
        raise ValueError("B3 cohort canonical IDs invalid or duplicated")
    return rows


def current_primary_drift(row: dict[str, Any], current: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    cid = row["canonicalId"]
    current_row = current.get(cid)
    drifts: list[dict[str, Any]] = []
    for provider in PRIMARY:
        frozen = row.get("providers", {}).get(provider, {})
        frozen_present = bool(frozen.get("discoveredInInventory"))
        frozen_identity = _identity(provider, frozen.get("inventoryIdentity"))
        current_mapping = None
        if isinstance(current_row, dict):
            mappings = current_row.get("providers")
            if isinstance(mappings, dict):
                current_mapping = mappings.get(provider)
        current_present = isinstance(current_mapping, dict) and current_mapping.get("available") is True
        current_identity = _identity(provider, current_mapping)
        if frozen_present != current_present or (frozen_present and current_identity != frozen_identity):
            drifts.append({
                "provider": provider,
                "frozenPresent": frozen_present,
                "currentPresent": current_present,
                "frozenIdentity": list(frozen_identity) if frozen_identity else None,
                "currentIdentity": list(current_identity) if current_identity else None,
            })
    return drifts


def providers_for_runtime(row: dict[str, Any]) -> list[str]:
    decision = row.get("decision", {}).get("decision")
    providers = row.get("providers", {})
    if decision == NO_RUNTIME_DECISION:
        return []
    if decision == "B3_TARGETED_PRIMARY_DISCOVERY_VALIDATION":
        selected = []
        for provider in PRIMARY:
            state = providers.get(provider, {})
            identity = state.get("farmIdentity")
            if state.get("presentInFarm") is True and isinstance(identity, dict) and identity.get("file"):
                selected.append(provider)
        return selected
    selected = []
    for provider in PRIMARY:
        state = providers.get(provider, {})
        identity = state.get("farmIdentity")
        if (
            state.get("presentInFarm") is True
            and state.get("discoveredInInventory") is True
            and state.get("identityAligned") is True
            and isinstance(identity, dict)
            and identity.get("file")
        ):
            selected.append(provider)
    return selected


def build_plan(
    b2: dict[str, Any],
    current_inventory: dict[str, Any],
    *,
    current_inventory_commit: str,
    foundation_commit: str,
    uma_candidate: str,
    uma_lkg: str,
    gekkoushi_candidate: str,
    gekkoushi_lkg: str,
) -> dict[str, Any]:
    rows = validate_b2(b2)
    current = index_inventory(current_inventory)
    drift: list[dict[str, Any]] = []
    no_runtime: list[dict[str, Any]] = []
    per_provider: dict[str, list[dict[str, Any]]] = {provider: [] for provider in PRIMARY}
    source_rows: list[dict[str, Any]] = []

    for row in sorted(rows, key=lambda x: x["canonicalId"]):
        cid = row["canonicalId"]
        row_drift = current_primary_drift(row, current)
        if row_drift:
            drift.append({"canonicalId": cid, "changes": row_drift})
        decision = row["decision"]["decision"]
        selected = providers_for_runtime(row)
        source_rows.append({
            "canonicalId": cid,
            "displayName": row.get("displayName"),
            "decision": decision,
            "finding": row.get("finding"),
            "runtimeProviders": selected,
        })
        if decision == NO_RUNTIME_DECISION:
            if selected:
                raise ValueError(f"{cid}: no-runtime decision unexpectedly selected providers")
            no_runtime.append({
                "canonicalId": cid,
                "displayName": row.get("displayName"),
                "classification": "NO_PRIMARY_IMPLEMENTATION_AT_B3_SNAPSHOT",
                "nextAction": "PRIMARY_COVERAGE_DECISION_OR_TARGETED_REPAIR",
            })
            continue
        if decision not in RUNTIME_DECISIONS:
            raise ValueError(f"{cid}: unsupported B3 decision {decision}")
        if not selected:
            no_runtime.append({
                "canonicalId": cid,
                "displayName": row.get("displayName"),
                "classification": "NO_EXECUTABLE_PRIMARY_LOCATOR",
                "nextAction": "TARGETED_REPAIR_REQUIRED",
            })
            continue
        for provider in selected:
            identity = row["providers"][provider]["farmIdentity"]
            per_provider[provider].append({
                "canonicalId": cid,
                "providers": [provider],
                "upstreamIdentities": {provider: identity},
                "attempts": 0,
                "previousAttempts": 0,
                "lifetimeAttempts": 0,
                "baselineReset": False,
            })

    if drift:
        raise ValueError(
            "current primary inventory drift touches frozen B3 cohort: "
            + ", ".join(item["canonicalId"] for item in drift)
        )

    runtime_pairs = sum(len(v) for v in per_provider.values())
    return {
        "schemaVersion": 1,
        "phase": "TRACK_B_BATCH_3_RUNTIME_VALIDATION",
        "readOnly": True,
        "status": "PLANNED",
        "provenance": {
            "b2ControlCommit": b2.get("provenance", {}).get("controlCommit"),
            "b2InventoryCommit": b2.get("provenance", {}).get("inventoryCommit"),
            "b2FoundationCommit": b2.get("provenance", {}).get("foundationCommit"),
            "currentInventoryCommit": current_inventory_commit,
            "foundationCommitAtB3Start": foundation_commit,
            "providerRefs": {
                "uma": {"candidate": uma_candidate, "lkg": uma_lkg},
                "gekkoushi": {"candidate": gekkoushi_candidate, "lkg": gekkoushi_lkg},
            },
        },
        "summary": {
            "cohortRows": len(rows),
            "noRuntimeRows": len(no_runtime),
            "runtimeSourceRows": sum(1 for row in source_rows if row["runtimeProviders"]),
            "runtimeProviderPairs": runtime_pairs,
            "umaPairs": len(per_provider["uma"]),
            "gekkoushiPairs": len(per_provider["gekkoushi"]),
            "primaryInventoryDriftRows": len(drift),
        },
        "sources": source_rows,
        "noRuntime": no_runtime,
        "providerPlans": {
            provider: {"schemaVersion": 2, "items": items}
            for provider, items in per_provider.items()
        },
        "safety": {
            "mutatesAuthorityState": False,
            "mutatesLastKnownGood": False,
            "mutatesRetryHeld": False,
            "mutatesCanonicalIds": False,
            "promotesProvider": False,
            "approvesOverlay": False,
            "keiyoushiRuntimeUsed": False,
        },
    }


def _results_by_key(value: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in value.get("results", []):
        if not isinstance(row, dict):
            continue
        cid, provider = row.get("canonicalId"), row.get("provider")
        if isinstance(cid, str) and provider in PRIMARY:
            result[(cid, provider)] = row
    return result


def _parser_state(row: dict[str, Any] | None) -> str:
    if not isinstance(row, dict):
        return "MISSING"
    if (
        row.get("status") == "PASS"
        and row.get("parserExecution") is True
        and row.get("detailsTraversal") is True
        and row.get("chapterTraversal") is True
        and row.get("pageTraversal") is True
    ):
        return "PASS"
    if row.get("status") == "FAIL":
        return "FAIL"
    return "INDETERMINATE"


def _profile_by_id(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["canonicalId"]: row
        for row in value.get("results", [])
        if isinstance(row, dict) and isinstance(row.get("canonicalId"), str)
    }


def _profile_member(profile: dict[str, Any] | None, provider: str) -> dict[str, Any] | None:
    if not isinstance(profile, dict):
        return None
    members = profile.get("evidence", {}).get("profile", {}).get("memberships", [])
    for member in members:
        if isinstance(member, dict) and member.get("provider") == provider:
            return member
    return None


def finalize(
    plan: dict[str, Any],
    *,
    candidate_profiles: dict[str, dict[str, Any]],
    lkg_profiles: dict[str, dict[str, Any]],
    candidate_parser: dict[str, Any],
    lkg_parser: dict[str, Any],
) -> dict[str, Any]:
    if plan.get("phase") != "TRACK_B_BATCH_3_RUNTIME_VALIDATION" or plan.get("readOnly") is not True:
        raise ValueError("invalid B3 plan")
    cand_parser = _results_by_key(candidate_parser)
    old_parser = _results_by_key(lkg_parser)
    cand_profiles = {p: _profile_by_id(v) for p, v in candidate_profiles.items()}
    old_profiles = {p: _profile_by_id(v) for p, v in lkg_profiles.items()}

    pair_rows: list[dict[str, Any]] = []
    per_source_pass: dict[str, list[str]] = {}
    for provider, provider_plan in plan.get("providerPlans", {}).items():
        if provider not in PRIMARY:
            raise ValueError(f"unexpected provider plan: {provider}")
        for item in provider_plan.get("items", []):
            cid = item["canonicalId"]
            candidate = _parser_state(cand_parser.get((cid, provider)))
            lkg = _parser_state(old_parser.get((cid, provider)))
            if candidate == "PASS" and lkg == "PASS":
                delta = "STABLE_PASS"
            elif candidate == "PASS" and lkg != "PASS":
                delta = "CANDIDATE_RECOVERY"
            elif candidate != "PASS" and lkg == "PASS":
                delta = "CANDIDATE_REGRESSION"
            elif candidate == "FAIL" and lkg == "FAIL":
                delta = "NO_PROVEN_RUNTIME"
            else:
                delta = "INDETERMINATE"
            if candidate == "PASS":
                per_source_pass.setdefault(cid, []).append(provider)
            pair_rows.append({
                "canonicalId": cid,
                "provider": provider,
                "candidate": {
                    "parser": candidate,
                    "profile": _profile_member(cand_profiles[provider].get(cid), provider),
                    "result": cand_parser.get((cid, provider)),
                },
                "lkg": {
                    "parser": lkg,
                    "profile": _profile_member(old_profiles[provider].get(cid), provider),
                    "result": old_parser.get((cid, provider)),
                },
                "delta": delta,
            })

    no_runtime_ids = {row["canonicalId"] for row in plan.get("noRuntime", [])}
    decisions: list[dict[str, Any]] = []
    for source in plan.get("sources", []):
        cid = source["canonicalId"]
        passed = sorted(per_source_pass.get(cid, []))
        runtime = source.get("runtimeProviders", [])
        if cid in no_runtime_ids and not runtime:
            decision = "B3_PRIMARY_COVERAGE_REPAIR_REQUIRED"
            next_phase = "TRACK_B_BATCH_3"
            reason = "No executable UMA/Gekkoushi primary implementation exists at the frozen B3 snapshot."
        elif passed:
            decision = "B3_PRIMARY_RUNTIME_PROVEN"
            next_phase = "TRACK_B_BATCH_4"
            reason = "At least one primary provider passed real parser traversal on the candidate snapshot."
        else:
            decision = "B3_TARGETED_PRIMARY_REPAIR_REQUIRED"
            next_phase = "TRACK_B_BATCH_3"
            reason = "No candidate primary provider produced complete real parser traversal evidence."
        decisions.append({
            "canonicalId": cid,
            "displayName": source.get("displayName"),
            "inputDecision": source.get("decision"),
            "testedProviders": runtime,
            "passingCandidateProviders": passed,
            "decision": decision,
            "nextPhase": next_phase,
            "reason": reason,
        })

    counts = Counter(row["decision"] for row in decisions)
    deltas = Counter(row["delta"] for row in pair_rows)
    return {
        "schemaVersion": 1,
        "phase": "TRACK_B_BATCH_3_RUNTIME_VALIDATION",
        "readOnly": True,
        "status": "COMPLETE_WITH_RUNTIME_EVIDENCE",
        "provenance": plan.get("provenance"),
        "summary": {
            "cohortRows": len(decisions),
            "runtimeProviderPairs": len(pair_rows),
            "decisions": dict(sorted(counts.items())),
            "differential": dict(sorted(deltas.items())),
            "batch4Rows": sum(1 for row in decisions if row["nextPhase"] == "TRACK_B_BATCH_4"),
            "remainingBatch3Rows": sum(1 for row in decisions if row["nextPhase"] == "TRACK_B_BATCH_3"),
        },
        "decisions": decisions,
        "runtimeEvidence": pair_rows,
        "safety": plan.get("safety"),
    }


def markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Track B — Batch 3 Runtime Validation",
        "",
        f"- Cohort rows: **{s['cohortRows']}**",
        f"- Runtime provider pairs: **{s['runtimeProviderPairs']}**",
        f"- Routed to Batch 4: **{s['batch4Rows']}**",
        f"- Remaining in Batch 3: **{s['remainingBatch3Rows']}**",
        "",
        "## Decisions",
        "",
        "| Canonical | Decision | Passing candidate primary | Next |",
        "|---|---|---|---|",
    ]
    for row in report["decisions"]:
        passes = ", ".join(row["passingCandidateProviders"]) or "—"
        lines.append(f"| `{row['canonicalId']}` | `{row['decision']}` | {passes} | `{row['nextPhase']}` |")
    lines += ["", "## Differential runtime evidence", "", "| Canonical | Provider | Candidate | LKG | Delta |", "|---|---|---|---|---|"]
    for row in report["runtimeEvidence"]:
        lines.append(
            f"| `{row['canonicalId']}` | `{row['provider']}` | `{row['candidate']['parser']}` | "
            f"`{row['lkg']['parser']}` | `{row['delta']}` |"
        )
    return "\n".join(lines) + "\n"


def cmd_plan(args: argparse.Namespace) -> None:
    report = build_plan(
        load(args.b2_report),
        load(args.current_inventory),
        current_inventory_commit=args.current_inventory_commit,
        foundation_commit=args.foundation_commit,
        uma_candidate=args.uma_candidate,
        uma_lkg=args.uma_lkg,
        gekkoushi_candidate=args.gekkoushi_candidate,
        gekkoushi_lkg=args.gekkoushi_lkg,
    )
    save(args.output, report)
    output_dir = Path(args.provider_plan_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for provider, value in report["providerPlans"].items():
        save(output_dir / f"{provider}.json", value)


def cmd_finalize(args: argparse.Namespace) -> None:
    candidate_profiles = {p: load(getattr(args, f"candidate_{p}_profile")) for p in PRIMARY}
    lkg_profiles = {p: load(getattr(args, f"lkg_{p}_profile")) for p in PRIMARY}
    report = finalize(
        load(args.plan),
        candidate_profiles=candidate_profiles,
        lkg_profiles=lkg_profiles,
        candidate_parser=load(args.candidate_parser),
        lkg_parser=load(args.lkg_parser),
    )
    save(args.output, report)
    if args.markdown_output:
        Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--b2-report", required=True)
    p.add_argument("--current-inventory", required=True)
    p.add_argument("--current-inventory-commit", required=True)
    p.add_argument("--foundation-commit", required=True)
    p.add_argument("--uma-candidate", required=True)
    p.add_argument("--uma-lkg", required=True)
    p.add_argument("--gekkoushi-candidate", required=True)
    p.add_argument("--gekkoushi-lkg", required=True)
    p.add_argument("--provider-plan-dir", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_plan)

    f = sub.add_parser("finalize")
    f.add_argument("--plan", required=True)
    for baseline in ("candidate", "lkg"):
        for provider in PRIMARY:
            f.add_argument(f"--{baseline}-{provider}-profile", required=True)
    f.add_argument("--candidate-parser", required=True)
    f.add_argument("--lkg-parser", required=True)
    f.add_argument("--output", required=True)
    f.add_argument("--markdown-output")
    f.set_defaults(func=cmd_finalize)
    return root


def main() -> int:
    args = parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
