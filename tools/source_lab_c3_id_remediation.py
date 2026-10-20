#!/usr/bin/env python3
"""Track C C3 remediation revalidation for the three unresolved ID sources.

This phase is deliberately read-only. It consumes the frozen C2/C3/C4 evidence,
builds a source-scoped runtime plan, permits an explicit unauthenticated public
smoke only where the plan says so, and classifies the resulting evidence without
mutating Compatibility Farm, LKG, Retry/Held, canonical IDs, provider selection,
or consumer packaging.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

PHASE = "TRACK_C_C3_ID_REMEDIATION_REVALIDATION"
C2_PHASE = "TRACK_C_BATCH_2_ID_CAPABILITY_HEALTH_DECISION"
C3_PHASE = "TRACK_C_BATCH_3"
C4_PHASE = "TRACK_C_BATCH_4_ID_ADOPTION_DRIFT"
NO_AUTH = "NO_AUTH"

LUMOS = "miyorare:inventory-id:LUMOSKOMIK"
MANGABALL = "miyorare:inventory-id:MANGABALLINDONESIAN"
SOFTKOMIK = "miyorare:inventory-id:SOFTKOMIK"
REMEDIATION_IDS = (LUMOS, MANGABALL, SOFTKOMIK)
ROUTES = {
    LUMOS: ("gekkoushi", "uma"),
    MANGABALL: ("uma",),
    SOFTKOMIK: ("uma",),
}
DOMAIN_RE = re.compile(r'(?:https?://)?([A-Za-z0-9.-]+\.[A-Za-z]{2,})')


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def by_id(rows: Any, *, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError(f"{label} must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("canonicalId"), str):
            continue
        cid = row["canonicalId"]
        if cid in result:
            raise ValueError(f"duplicate {label} row: {cid}")
        result[cid] = row
    return result


def validate_boundary(c2: dict[str, Any], c3: dict[str, Any], c4: dict[str, Any]) -> None:
    if c2.get("phase") != C2_PHASE or c2.get("readOnly") is not True or c2.get("language") != "id":
        raise ValueError("invalid C2 ID boundary")
    if c3.get("phase") != C3_PHASE or c3.get("readOnly") is not True:
        raise ValueError("invalid C3 boundary")
    if c3.get("summary", {}).get("remediationRequired") != 3:
        raise ValueError("C3 remediation count is not 3")
    if c4.get("phase") != C4_PHASE or c4.get("readOnly") is not True:
        raise ValueError("invalid C4 boundary")
    remediation = c4.get("remediation")
    if not isinstance(remediation, dict):
        raise ValueError("C4 remediation boundary missing")
    if remediation.get("remainingRows") != 3:
        raise ValueError("C4 remediation count is not 3")
    if tuple(remediation.get("canonicalIds") or ()) != REMEDIATION_IDS:
        raise ValueError("C4 remediation IDs drifted")


def provider_identity(assessment: dict[str, Any], provider: str) -> dict[str, Any]:
    row = assessment.get("providers", {}).get(provider, {})
    if not isinstance(row, dict):
        raise ValueError(f"provider row missing: {provider}")
    identity = row.get("inventoryIdentity") or row.get("farmIdentity")
    if not isinstance(identity, dict):
        raise ValueError(f"provider identity missing: {provider}")
    return identity


def source_domain(root: Path, identity: dict[str, Any], provider: str) -> str | None:
    if provider == "keiyoushi":
        base = identity.get("baseUrl")
        if isinstance(base, str):
            match = DOMAIN_RE.search(base)
            return match.group(1).lower() if match else None
        return None
    locator = identity.get("file")
    if not isinstance(locator, str):
        return None
    path = root / locator
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")
    patterns = (
        r'ConfigKey\.Domain\(\s*"([^"]+)"\s*\)',
        r'\bbaseUrl\s*=\s*"https?://([^"/]+)',
        r'Parser\([^)]*"([A-Za-z0-9.-]+\.[A-Za-z]{2,})"\s*\)',
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            return match.group(1).lower()
    return None


def build_plan(
    c2: dict[str, Any],
    c3: dict[str, Any],
    c4: dict[str, Any],
    *,
    uma_root: Path,
    gekkoushi_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_boundary(c2, c3, c4)
    assessments = by_id(c2.get("sourceAssessments"), label="C2 sourceAssessments")
    decisions = by_id(c3.get("decisions"), label="C3 decisions")

    items: list[dict[str, Any]] = []
    for cid in REMEDIATION_IDS:
        assessment = assessments.get(cid)
        prior = decisions.get(cid)
        if assessment is None or prior is None:
            raise ValueError(f"frozen evidence missing remediation source: {cid}")
        if prior.get("nextAction") != "C3_REMEDIATION_REQUIRED":
            raise ValueError(f"C3 no longer marks remediation required: {cid}")

        providers = list(ROUTES[cid])
        identities = {provider: provider_identity(assessment, provider) for provider in providers}
        item: dict[str, Any] = {
            "canonicalId": cid,
            "language": "id",
            "providers": providers,
            "upstreamIdentities": identities,
            "attempts": 0,
            "previousAttempts": 0,
            "lifetimeAttempts": 0,
            "baselineReset": False,
            "c3Decision": prior.get("decision"),
            "c3RuntimeState": prior.get("runtimeState"),
            "remediationIntent": {
                LUMOS: "COMPARE_CONSUMED_GEKKOUSHI_WITH_EXISTING_UMA_IMPLEMENTATION",
                MANGABALL: "CONFIRM_FACTUAL_UMA_HTTP_RUNTIME_STATE",
                SOFTKOMIK: "TEST_PUBLIC_RUNTIME_WITH_EXPLICIT_AUTH_CAPABILITY_OVERRIDE",
            }[cid],
        }
        if cid == SOFTKOMIK:
            item["allowUnauthenticatedLiveSmoke"] = True
            item["authOverrideScope"] = "PUBLIC_BROWSE_ONLY_NO_CREDENTIALS"
        items.append(item)

    lumos = assessments[LUMOS]
    structural = {
        "lumos": {
            "gekkoushiDomain": source_domain(
                gekkoushi_root, provider_identity(lumos, "gekkoushi"), "gekkoushi"
            ),
            "umaDomain": source_domain(uma_root, provider_identity(lumos, "uma"), "uma"),
            "keiyoushiBaseUrl": provider_identity(lumos, "keiyoushi").get("baseUrl"),
        },
        "softkomik": {
            "keiyoushiBaseUrl": provider_identity(assessments[SOFTKOMIK], "keiyoushi").get("baseUrl"),
            "umaAuthCapable": True,
            "noCredentialsInjected": True,
        },
    }

    plan = {
        "schemaVersion": 2,
        "phase": PHASE,
        "language": "id",
        "readOnly": True,
        "count": len(items),
        "items": items,
        "structuralEvidence": structural,
        "provenance": {
            "c2": c2.get("provenance"),
            "c3": c3.get("provenance"),
            "c4BaselineRefs": c4.get("baselineRefs"),
        },
        "safetyBoundary": {
            "mutateFarmAuthority": False,
            "mutateLastKnownGood": False,
            "mutateRetryHeld": False,
            "mutateCanonicalId": False,
            "mutateConsumerPackaging": False,
            "autoAdoptProvider": False,
            "injectCredentials": False,
        },
    }
    return plan, {"schemaVersion": 2, "count": len(items), "items": items}


def prepare_profiles(plan: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    if plan.get("phase") != PHASE or plan.get("readOnly") is not True:
        raise ValueError("invalid remediation plan")
    allowed = {
        item["canonicalId"]
        for item in plan.get("items", [])
        if item.get("allowUnauthenticatedLiveSmoke") is True
    }
    rows: list[dict[str, Any]] = []
    for raw in profiles.get("results", []):
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        cid = row.get("canonicalId")
        if cid in allowed and row.get("authType") != NO_AUTH:
            original = row.get("authType")
            row["originalAuthType"] = original
            row["authType"] = NO_AUTH
            row["authSmokeOverride"] = True
            row["authSmokeOverrideScope"] = "PUBLIC_BROWSE_ONLY_NO_CREDENTIALS"
        rows.append(row)
    result = dict(profiles)
    result["results"] = rows
    result["remediationAuthOverrides"] = sorted(allowed)
    return result


def result_map(results: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in results.get("results", []):
        if (
            isinstance(row, dict)
            and isinstance(row.get("canonicalId"), str)
            and isinstance(row.get("provider"), str)
        ):
            mapped[(row["canonicalId"], row["provider"])] = row
    return mapped


def runtime_pass(row: dict[str, Any] | None) -> bool:
    return bool(
        row
        and row.get("status") == "PASS"
        and row.get("parserExecution") is True
        and row.get("detailsTraversal") is True
        and row.get("chapterTraversal") is True
        and row.get("pageExtraction") is True
    )


def classify(cid: str, results: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    safety = {
        "readOnly": True,
        "authorityMutation": False,
        "providerAdoption": False,
        "credentialInjection": False,
    }
    if cid == LUMOS:
        g = results.get((cid, "gekkoushi"))
        u = results.get((cid, "uma"))
        gp, up = runtime_pass(g), runtime_pass(u)
        if up and not gp:
            decision = "LUMOS_PROVIDER_DIVERGENCE_CONFIRMED"
            next_action = "C4_PROVIDER_RECONCILIATION_REQUIRED"
            remediation_resolved = True
            lifecycle_handoff = True
        elif gp:
            decision = "LUMOS_CONSUMED_GEKKOUSHI_RUNTIME_REVALIDATED"
            next_action = "C4_REVIEW_PROVIDER_EVIDENCE"
            remediation_resolved = True
            lifecycle_handoff = True
        elif up:
            decision = "LUMOS_ALTERNATE_UMA_RUNTIME_VALIDATED"
            next_action = "C4_PROVIDER_RECONCILIATION_REQUIRED"
            remediation_resolved = True
            lifecycle_handoff = True
        else:
            decision = "LUMOS_RUNTIME_REMEDIATION_REMAINS"
            next_action = "C3_REMEDIATION_REQUIRED"
            remediation_resolved = False
            lifecycle_handoff = False
        return {
            "canonicalId": cid,
            "decision": decision,
            "nextAction": next_action,
            "remediationResolved": remediation_resolved,
            "lifecycleHandoffRequired": lifecycle_handoff,
            "runtime": {"gekkoushi": g, "uma": u},
            "safety": safety,
        }

    row = results.get((cid, "uma"))
    passed = runtime_pass(row)
    if cid == MANGABALL:
        decision = (
            "MANGABALL_RUNTIME_REVALIDATED"
            if passed
            else "MANGABALL_UPSTREAM_RUNTIME_FAILURE_CONFIRMED"
        )
        next_action = "C4_REVIEW_RUNTIME_EVIDENCE" if passed else "C3_REMEDIATION_REQUIRED"
        lifecycle_handoff = passed
    elif cid == SOFTKOMIK:
        decision = (
            "SOFTKOMIK_PUBLIC_RUNTIME_VALIDATED_WITH_AUTH_CAPABILITY"
            if passed
            else "SOFTKOMIK_RUNTIME_FAILURE_AFTER_PUBLIC_AUTH_OVERRIDE"
        )
        next_action = "C4_REVIEW_CURATED_ADOPTION" if passed else "C3_REMEDIATION_REQUIRED"
        lifecycle_handoff = passed
    else:
        raise ValueError(f"unknown remediation source: {cid}")
    return {
        "canonicalId": cid,
        "decision": decision,
        "nextAction": next_action,
        "remediationResolved": passed,
        "lifecycleHandoffRequired": lifecycle_handoff,
        "runtime": {"uma": row},
        "safety": safety,
    }


def build_report(plan: dict[str, Any], live_results: dict[str, Any]) -> dict[str, Any]:
    if plan.get("phase") != PHASE or plan.get("readOnly") is not True:
        raise ValueError("invalid remediation plan")
    mapped = result_map(live_results)
    decisions = [classify(cid, mapped) for cid in REMEDIATION_IDS]
    remaining = [row["canonicalId"] for row in decisions if not row["remediationResolved"]]
    handoffs = [row["canonicalId"] for row in decisions if row["lifecycleHandoffRequired"]]
    counts = Counter(row["decision"] for row in decisions)
    if remaining:
        status = "C3_REMEDIATION_REVALIDATED_WITH_FINDINGS"
    elif handoffs:
        status = "C3_REMEDIATION_RESOLVED_WITH_C4_HANDOFF"
    else:
        status = "C3_REMEDIATION_RESOLVED"
    track_closed = not remaining and not handoffs
    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "language": "id",
        "readOnly": True,
        "status": status,
        "trackCClosed": track_closed,
        "decisions": decisions,
        "summary": {
            "sources": 3,
            "resolved": 3 - len(remaining),
            "remaining": len(remaining),
            "remainingCanonicalIds": remaining,
            "lifecycleHandoffs": len(handoffs),
            "lifecycleHandoffCanonicalIds": handoffs,
            "decisions": dict(sorted(counts.items())),
        },
        "structuralEvidence": plan.get("structuralEvidence"),
        "safetyBoundary": plan.get("safetyBoundary"),
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track C C3 — ID Remediation Revalidation",
        "",
        f"- Status: `{report['status']}`",
        f"- Resolved remediation rows: `{report['summary']['resolved']}`",
        f"- Remaining remediation rows: `{report['summary']['remaining']}`",
        f"- Lifecycle handoffs: `{report['summary']['lifecycleHandoffs']}`",
        f"- Track C closed: `{str(report['trackCClosed']).lower()}`",
        "- Authority/consumer mutation: `none`",
        "- Credentials injected: `none`",
        "",
        "| Canonical ID | Decision | Next action |",
        "|---|---|---|",
    ]
    for row in report["decisions"]:
        lines.append(f"| `{row['canonicalId']}` | `{row['decision']}` | `{row['nextAction']}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan")
    p.add_argument("--c2-report", required=True)
    p.add_argument("--c3-report", required=True)
    p.add_argument("--c4-report", required=True)
    p.add_argument("--uma-root", required=True)
    p.add_argument("--gekkoushi-root", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--runtime-plan", required=True)

    a = sub.add_parser("prepare-profiles")
    a.add_argument("--plan", required=True)
    a.add_argument("--profiles", required=True)
    a.add_argument("--output", required=True)

    r = sub.add_parser("report")
    r.add_argument("--plan", required=True)
    r.add_argument("--live-results", required=True)
    r.add_argument("--output", required=True)
    r.add_argument("--markdown-output", required=True)

    args = parser.parse_args()
    if args.command == "plan":
        plan, runtime = build_plan(
            load(args.c2_report),
            load(args.c3_report),
            load(args.c4_report),
            uma_root=Path(args.uma_root),
            gekkoushi_root=Path(args.gekkoushi_root),
        )
        save(args.output, plan)
        save(args.runtime_plan, runtime)
    elif args.command == "prepare-profiles":
        save(args.output, prepare_profiles(load(args.plan), load(args.profiles)))
    else:
        report = build_report(load(args.plan), load(args.live_results))
        save(args.output, report)
        Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
