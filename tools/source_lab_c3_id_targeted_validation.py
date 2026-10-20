#!/usr/bin/env python3
"""Track C Batch 3: provider-role-aware ID targeted validation.

Consumes the exact read-only C2 boundary, inspects frozen upstream snapshots,
builds only source-scoped runtime plans, and emits read-only C3 dispositions.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

C3 = "TRACK_C_BATCH_3"
PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
RUNTIME_TARGETS = {
    "miyorare:inventory-id:LUMOSKOMIK": "gekkoushi",
    "miyorare:inventory-id:MANGABALLINDONESIAN": "uma",
    "miyorare:inventory-id:SOFTKOMIK": "uma",
    "miyorare:inventory-id:THRIVEMOE": "uma",
}
REFERENCE_TARGETS = {
    "miyorare:inventory-id:DAILYSUKA",
    "miyorare:inventory-id:IKIRU",
    "miyorare:inventory-id:MIKOROKU",
    "miyorare:inventory-id:PORNHWA18",
}
EXPECTED_COHORT = set(RUNTIME_TARGETS) | REFERENCE_TARGETS


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def c3_rows(c2: dict[str, Any]) -> list[dict[str, Any]]:
    if c2.get("phase") != "TRACK_C_BATCH_2_ID_CAPABILITY_HEALTH":
        raise ValueError("unexpected C2 phase")
    if c2.get("readOnly") is not True or c2.get("language") != "id":
        raise ValueError("C2 must be read-only ID evidence")
    rows = c2.get("c3Candidates")
    if not isinstance(rows, list):
        raise ValueError("C2 c3Candidates missing")
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("canonicalId"), str):
            raise ValueError("invalid C3 candidate")
        cid = row["canonicalId"]
        if cid in by_id:
            raise ValueError(f"duplicate C3 candidate: {cid}")
        by_id[cid] = row
    if set(by_id) != EXPECTED_COHORT:
        raise ValueError(f"C3 cohort mismatch: {sorted(by_id)}")
    if c2.get("summary", {}).get("c3CanonicalSources") != len(EXPECTED_COHORT):
        raise ValueError("C2 C3 canonical source count mismatch")
    if c2.get("summary", {}).get("c3FindingRows") != 9:
        raise ValueError("C2 C3 finding-row count mismatch")
    return [by_id[cid] for cid in sorted(by_id)]


def assessment_map(c2: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = c2.get("sourceAssessments")
    if not isinstance(rows, list):
        raise ValueError("C2 sourceAssessments missing")
    result = {
        row["canonicalId"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("canonicalId"), str)
    }
    missing = EXPECTED_COHORT - set(result)
    if missing:
        raise ValueError(f"C2 assessments missing C3 sources: {sorted(missing)}")
    return result


def locator(identity: dict[str, Any], provider: str) -> str | None:
    key = "module" if provider == "keiyoushi" else "file"
    value = identity.get(key)
    return value if isinstance(value, str) and value else None


def git_last_touch(root: Path, path: str) -> dict[str, Any] | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "log", "-1", "--format=%H%x00%s", "--", path],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    if not out:
        return None
    sha, _, subject = out.partition("\x00")
    return {"commit": sha, "subject": subject}


def find_relocations(root: Path, module: str) -> list[str]:
    name = Path(module).name
    src = root / "src"
    if not src.is_dir():
        return []
    result: list[str] = []
    for language in sorted(src.iterdir()):
        candidate = language / name
        if language.is_dir() and candidate.is_dir():
            rel = candidate.relative_to(root).as_posix()
            if rel != module:
                result.append(rel)
    return result


def reference_evidence(
    cid: str,
    assessment: dict[str, Any],
    keiyoushi_root: Path,
) -> dict[str, Any]:
    provider = assessment.get("providers", {}).get("keiyoushi", {})
    farm = provider.get("farmIdentity") if isinstance(provider, dict) else None
    inventory = provider.get("inventoryIdentity") if isinstance(provider, dict) else None
    farm = farm if isinstance(farm, dict) else {}
    inventory = inventory if isinstance(inventory, dict) else {}
    module = locator(farm or inventory, "keiyoushi")
    if not module:
        return {"state": "NO_REFERENCE_IDENTITY", "module": None}

    exists = (keiyoushi_root / module).is_dir()
    relocations = find_relocations(keiyoushi_root, module) if not exists else []
    last_touch = git_last_touch(keiyoushi_root, module)

    farm_source_id = str(farm.get("sourceId") or "")
    inventory_source_id = str(inventory.get("sourceId") or "")
    if exists and farm_source_id and inventory_source_id and farm_source_id != inventory_source_id:
        state = "REFERENCE_SOURCE_ID_MIGRATION_PRESENT"
    elif exists:
        state = "REFERENCE_PRESENT"
    elif relocations:
        state = "REFERENCE_LANGUAGE_RELOCATED"
    else:
        state = "REFERENCE_REMOVED_UPSTREAM"

    return {
        "state": state,
        "module": module,
        "modulePresent": exists,
        "relocations": relocations,
        "lastTouch": last_touch,
        "farmIdentity": farm or None,
        "inventoryIdentity": inventory or None,
    }


def runtime_item(
    cid: str,
    assessment: dict[str, Any],
    provider: str,
    root: Path,
) -> dict[str, Any] | None:
    prow = assessment.get("providers", {}).get(provider, {})
    if not isinstance(prow, dict):
        return None
    identity = prow.get("inventoryIdentity") or prow.get("farmIdentity")
    if not isinstance(identity, dict):
        return None
    loc = locator(identity, provider)
    if not loc or not (root / loc).is_file():
        return None
    return {
        "canonicalId": cid,
        "language": "id",
        "providers": [provider],
        "upstreamIdentities": {provider: identity},
        "attempts": 0,
        "previousAttempts": 0,
        "lifetimeAttempts": 0,
        "baselineReset": False,
    }


def build_plan(
    c2: dict[str, Any],
    *,
    keiyoushi_root: Path,
    candidate_roots: dict[str, Path],
    lkg_roots: dict[str, Path],
    commits: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    candidates = c3_rows(c2)
    assessments = assessment_map(c2)
    items: list[dict[str, Any]] = []
    candidate_runtime: list[dict[str, Any]] = []
    lkg_runtime: list[dict[str, Any]] = []

    for candidate in candidates:
        cid = candidate["canonicalId"]
        assessment = assessments[cid]
        item: dict[str, Any] = {
            "canonicalId": cid,
            "displayName": assessment.get("displayName"),
            "c2Reasons": list(candidate.get("reasons") or []),
            "consumerCoverageProviders": list(assessment.get("currentConsumerCoverageProviders") or []),
            "providerRoles": {
                provider: assessment.get("providers", {}).get(provider, {}).get("consumerRole")
                for provider in PROVIDERS
            },
        }
        if cid in REFERENCE_TARGETS:
            item["referenceEvidence"] = reference_evidence(cid, assessment, keiyoushi_root)
        if cid in RUNTIME_TARGETS:
            provider = RUNTIME_TARGETS[cid]
            item["runtimeProvider"] = provider
            c = runtime_item(cid, assessment, provider, candidate_roots[provider])
            l = runtime_item(cid, assessment, provider, lkg_roots[provider])
            item["candidateImplementationPresent"] = c is not None
            item["lkgImplementationPresent"] = l is not None
            if c is not None:
                candidate_runtime.append(c)
            if l is not None:
                lkg_runtime.append(l)
        items.append(item)

    plan = {
        "schemaVersion": 1,
        "phase": C3,
        "language": "id",
        "readOnly": True,
        "provenance": {
            "c2": c2.get("provenance"),
            "providerCommits": commits,
        },
        "c2FindingRows": c2["summary"]["c3FindingRows"],
        "count": len(items),
        "items": items,
        "safetyBoundary": {
            "mutateFarmAuthority": False,
            "mutateLastKnownGood": False,
            "mutateRetryHeld": False,
            "mutateCanonicalId": False,
            "mutateConsumerPackaging": False,
            "autoAdoptProvider": False,
        },
    }
    runtime_common = {"schemaVersion": 2}
    return (
        plan,
        {**runtime_common, "side": "candidate", "count": len(candidate_runtime), "items": candidate_runtime},
        {**runtime_common, "side": "lkg", "count": len(lkg_runtime), "items": lkg_runtime},
    )


def result_map(results: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in results.get("results", []):
        if isinstance(row, dict) and isinstance(row.get("canonicalId"), str) and row.get("provider") in {"uma", "gekkoushi"}:
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


def disposition(item: dict[str, Any], candidate: dict[str, Any] | None, lkg: dict[str, Any] | None) -> dict[str, Any]:
    cid = item["canonicalId"]
    safety = {
        "readOnly": True,
        "mutateFarmAuthority": False,
        "mutateLastKnownGood": False,
        "mutateRetryHeld": False,
        "mutateCanonicalId": False,
        "mutateConsumerPackaging": False,
        "autoAdoptProvider": False,
    }

    if cid in REFERENCE_TARGETS:
        evidence = item["referenceEvidence"]
        state = evidence["state"]
        if state == "REFERENCE_SOURCE_ID_MIGRATION_PRESENT":
            decision = "REFERENCE_SOURCE_ID_MIGRATION_CONFIRMED"
            next_action = "C4_RECONCILE_REFERENCE_IDENTITY_WITHOUT_CANONICAL_ID_CHANGE"
        elif state == "REFERENCE_LANGUAGE_RELOCATED":
            decision = "REFERENCE_MOVED_OUT_OF_ID_SCOPE"
            next_action = "C4_REVIEW_STALE_ID_FARM_REFERENCE"
        elif state == "REFERENCE_REMOVED_UPSTREAM":
            decision = "REFERENCE_REMOVED_UPSTREAM"
            next_action = "C4_REVIEW_STALE_LKG_AND_DEPRECATION"
        else:
            decision = "REFERENCE_EVIDENCE_INCOMPLETE"
            next_action = "C3_REMEDIATION_REQUIRED"
        return {
            "canonicalId": cid,
            "decision": decision,
            "nextAction": next_action,
            "referenceEvidence": evidence,
            "safety": safety,
        }

    provider = item["runtimeProvider"]
    cpass = runtime_pass(candidate)
    lpass = runtime_pass(lkg)
    if cpass and lpass:
        runtime_state = "CANDIDATE_AND_LKG_PASS"
    elif cpass and not lpass:
        runtime_state = "CANDIDATE_PASS_LKG_NOT_PASSING_OR_ABSENT"
    elif not cpass and lpass:
        runtime_state = "CANDIDATE_REGRESSION"
    else:
        runtime_state = "CANDIDATE_NOT_VALIDATED"

    if cid == "miyorare:inventory-id:LUMOSKOMIK":
        if cpass:
            decision = "CONSUMED_GEKKOUSHI_RUNTIME_VALIDATED"
            next_action = "C4_CONSIDER_SOURCE_SCOPED_FARM_ENROLLMENT_RECONCILIATION"
        else:
            decision = "CONSUMED_GEKKOUSHI_RUNTIME_NOT_VALIDATED"
            next_action = "C3_REMEDIATION_REQUIRED"
    elif cid in {"miyorare:inventory-id:MANGABALLINDONESIAN", "miyorare:inventory-id:SOFTKOMIK"}:
        if cpass:
            decision = "UNCURATED_UMA_RUNTIME_VALIDATED"
            next_action = "C4_CONSIDER_CURATED_ADOPTION"
        else:
            decision = "UNCURATED_UMA_RUNTIME_NOT_VALIDATED"
            next_action = "C3_REMEDIATION_REQUIRED"
    else:
        if cpass:
            decision = "UNENROLLED_UMA_RUNTIME_VALIDATED"
            next_action = "C4_CONSIDER_SOURCE_SCOPED_ENROLLMENT_THEN_ADOPTION"
        else:
            decision = "UNENROLLED_UMA_RUNTIME_NOT_VALIDATED"
            next_action = "C3_REMEDIATION_REQUIRED"

    return {
        "canonicalId": cid,
        "provider": provider,
        "decision": decision,
        "runtimeState": runtime_state,
        "nextAction": next_action,
        "candidateRuntime": candidate,
        "lkgRuntime": lkg,
        "safety": safety,
    }


def build_report(plan: dict[str, Any], candidate_results: dict[str, Any], lkg_results: dict[str, Any]) -> dict[str, Any]:
    if plan.get("phase") != C3 or plan.get("readOnly") is not True:
        raise ValueError("invalid C3 plan")
    c_map = result_map(candidate_results)
    l_map = result_map(lkg_results)
    decisions: list[dict[str, Any]] = []
    for item in plan.get("items", []):
        cid = item["canonicalId"]
        provider = item.get("runtimeProvider")
        candidate = c_map.get((cid, provider)) if provider else None
        lkg = l_map.get((cid, provider)) if provider else None
        decisions.append(disposition(item, candidate, lkg))

    counts = Counter(row["decision"] for row in decisions)
    remediation = sum(1 for row in decisions if row["nextAction"] == "C3_REMEDIATION_REQUIRED")
    return {
        "schemaVersion": 1,
        "phase": C3,
        "language": "id",
        "readOnly": True,
        "status": "COMPLETE_WITH_FINDINGS" if remediation else "COMPLETE",
        "provenance": plan.get("provenance"),
        "decisions": decisions,
        "summary": {
            "canonicalSources": len(decisions),
            "c2FindingRowsCovered": plan.get("c2FindingRows"),
            "runtimeTargets": len(RUNTIME_TARGETS),
            "referenceTargets": len(REFERENCE_TARGETS),
            "remediationRequired": remediation,
            "decisions": dict(sorted(counts.items())),
        },
        "safetyBoundary": plan.get("safetyBoundary"),
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track C Batch 3 — ID Targeted Validation",
        "",
        f"- Status: `{report['status']}`",
        f"- Canonical sources: `{report['summary']['canonicalSources']}`",
        f"- C2 finding rows covered: `{report['summary']['c2FindingRowsCovered']}`",
        f"- Remediation required: `{report['summary']['remediationRequired']}`",
        "- Authority/consumer mutation: `none`",
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
    p.add_argument("--keiyoushi-root", required=True)
    p.add_argument("--uma-candidate-root", required=True)
    p.add_argument("--gekkoushi-candidate-root", required=True)
    p.add_argument("--uma-lkg-root", required=True)
    p.add_argument("--gekkoushi-lkg-root", required=True)
    p.add_argument("--keiyoushi-candidate-commit", required=True)
    p.add_argument("--uma-candidate-commit", required=True)
    p.add_argument("--gekkoushi-candidate-commit", required=True)
    p.add_argument("--uma-lkg-commit", required=True)
    p.add_argument("--gekkoushi-lkg-commit", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--candidate-runtime-plan", required=True)
    p.add_argument("--lkg-runtime-plan", required=True)

    r = sub.add_parser("report")
    r.add_argument("--plan", required=True)
    r.add_argument("--candidate-results", required=True)
    r.add_argument("--lkg-results", required=True)
    r.add_argument("--output", required=True)
    r.add_argument("--markdown-output", required=True)

    args = parser.parse_args()
    if args.command == "plan":
        c2 = load(args.c2_report)
        plan, candidate, lkg = build_plan(
            c2,
            keiyoushi_root=Path(args.keiyoushi_root),
            candidate_roots={"uma": Path(args.uma_candidate_root), "gekkoushi": Path(args.gekkoushi_candidate_root)},
            lkg_roots={"uma": Path(args.uma_lkg_root), "gekkoushi": Path(args.gekkoushi_lkg_root)},
            commits={
                "candidate": {
                    "keiyoushi": args.keiyoushi_candidate_commit,
                    "uma": args.uma_candidate_commit,
                    "gekkoushi": args.gekkoushi_candidate_commit,
                },
                "lkg": {
                    "uma": args.uma_lkg_commit,
                    "gekkoushi": args.gekkoushi_lkg_commit,
                },
            },
        )
        save(args.output, plan)
        save(args.candidate_runtime_plan, candidate)
        save(args.lkg_runtime_plan, lkg)
    else:
        report = build_report(load(args.plan), load(args.candidate_results), load(args.lkg_results))
        save(args.output, report)
        Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
