#!/usr/bin/env python3
"""Read-only Source Lab A7 Last-Known-Good safety audit.

The audit binds the three authoritative provider baselines (upstream registry,
runtime status, and compatibility registry), verifies that unapproved candidates
remain separated from active/LKG state, checks ACTIVE source version/LKG
consistency, and guards the exact promotion workflow's stale-write authority
markers. It never mutates Source Lab state.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")


class LkgSafetyError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LkgSafetyError(f"{path} must contain a JSON object")
    return value


def _sha(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX40.fullmatch(value.lower()))


def _violate(violations: list[str], condition: bool, message: str) -> None:
    if not condition:
        violations.append(message)


def audit_lkg_safety(
    upstream_registry: dict[str, Any],
    status: dict[str, Any],
    source_registry: dict[str, Any],
    promotion_workflow: str,
) -> dict[str, Any]:
    violations: list[str] = []
    warnings: list[str] = []

    _violate(violations, upstream_registry.get("schema") == 1, "upstream registry schema must be 1")
    _violate(violations, status.get("schema") == 3, "upstream status schema must be 3")

    upstream_providers = upstream_registry.get("providers")
    status_providers = status.get("providers")
    baselines = source_registry.get("providerBaselines")
    if not isinstance(upstream_providers, dict):
        upstream_providers = {}
        violations.append("upstream registry providers must be an object")
    if not isinstance(status_providers, dict):
        status_providers = {}
        violations.append("status providers must be an object")
    if not isinstance(baselines, dict):
        baselines = {}
        violations.append("compatibility providerBaselines must be an object")

    provider_names = sorted(set(upstream_providers) | set(status_providers) | set(baselines))
    provider_rows: list[dict[str, Any]] = []
    automation = status.get("automation") if isinstance(status.get("automation"), dict) else {}
    candidates = automation.get("candidates") if isinstance(automation.get("candidates"), dict) else {}

    for provider in provider_names:
        upstream = upstream_providers.get(provider)
        runtime = status_providers.get(provider)
        baseline = baselines.get(provider)
        if not isinstance(upstream, dict) or not isinstance(runtime, dict):
            violations.append(f"{provider}: provider missing from authoritative registry/status")
            continue

        upstream_lkg = upstream.get("lastKnownGood")
        upstream_base = upstream.get("upstreamBase")
        active = runtime.get("activeCommit")
        runtime_lkg = runtime.get("lastKnownGood")
        for label, value in (
            ("upstream lastKnownGood", upstream_lkg),
            ("upstreamBase", upstream_base),
            ("activeCommit", active),
            ("runtime lastKnownGood", runtime_lkg),
            ("compatibility baseline", baseline),
        ):
            _violate(violations, _sha(value), f"{provider}: {label} must be a 40-character SHA")

        if all(_sha(v) for v in (upstream_lkg, upstream_base, active, runtime_lkg, baseline)):
            _violate(violations, upstream_base == upstream_lkg, f"{provider}: upstreamBase != upstream lastKnownGood")
            _violate(violations, active == runtime_lkg, f"{provider}: activeCommit != runtime lastKnownGood")
            _violate(violations, runtime_lkg == upstream_lkg, f"{provider}: runtime LKG != upstream registry LKG")
            _violate(violations, baseline == runtime_lkg, f"{provider}: compatibility baseline != runtime LKG")

        candidate = candidates.get(provider)
        candidate_sha = None
        candidate_current = None
        if candidate is not None:
            if not isinstance(candidate, dict):
                violations.append(f"{provider}: automation candidate must be an object")
            else:
                candidate_sha = candidate.get("candidate")
                candidate_current = candidate.get("current")
                _violate(violations, _sha(candidate_sha), f"{provider}: candidate must be a 40-character SHA")
                _violate(violations, _sha(candidate_current), f"{provider}: candidate current must be a 40-character SHA")
                if _sha(candidate_current) and _sha(runtime_lkg):
                    _violate(violations, candidate_current == runtime_lkg, f"{provider}: candidate baseline is stale")
                if _sha(candidate_sha) and _sha(runtime_lkg) and candidate_sha != candidate_current:
                    _violate(violations, candidate_sha != runtime_lkg and candidate_sha != active,
                             f"{provider}: unapproved candidate leaked into active/LKG")

        staged = runtime.get("candidate")
        if staged is not None:
            if not isinstance(staged, dict):
                violations.append(f"{provider}: staged candidate must be an object")
            else:
                commit = staged.get("commit")
                expected = staged.get("expectedLastKnownGood")
                _violate(violations, _sha(commit), f"{provider}: staged candidate commit must be a SHA")
                if expected is not None:
                    _violate(violations, expected == runtime_lkg,
                             f"{provider}: staged candidate expectedLastKnownGood != runtime LKG")
                if _sha(commit) and _sha(runtime_lkg):
                    _violate(violations, commit != runtime_lkg and commit != active,
                             f"{provider}: staged candidate leaked into active/LKG")

        provider_rows.append({
            "provider": provider,
            "activeCommit": active,
            "lastKnownGood": runtime_lkg,
            "compatibilityBaseline": baseline,
            "candidate": candidate_sha,
            "candidateCurrent": candidate_current,
        })

    approval_candidate = status.get("approvalCandidate")
    approval_candidate_present = isinstance(approval_candidate, dict)
    if approval_candidate is not None and not approval_candidate_present:
        violations.append("approvalCandidate must be an object when present")
    if approval_candidate_present:
        _violate(violations, approval_candidate.get("state") == "WAITING_FOR_APPROVAL",
                 "approvalCandidate must remain WAITING_FOR_APPROVAL")
        pending_providers = approval_candidate.get("providers")
        if not isinstance(pending_providers, dict) or not pending_providers:
            violations.append("approvalCandidate providers must be non-empty")
        else:
            for provider, item in sorted(pending_providers.items()):
                runtime = status_providers.get(provider, {})
                if not isinstance(item, dict) or not isinstance(runtime, dict):
                    violations.append(f"{provider}: malformed approval candidate")
                    continue
                current = item.get("current")
                candidate = item.get("candidate")
                _violate(violations, current == runtime.get("lastKnownGood"),
                         f"{provider}: approval candidate current no longer matches LKG")
                _violate(violations, candidate != current,
                         f"{provider}: approval candidate must differ from current LKG")

    active_sources = 0
    active_memberships = 0
    source_mismatches: list[str] = []
    sources = source_registry.get("sources")
    if not isinstance(sources, list):
        violations.append("compatibility sources must be a list")
        sources = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        enrollment = source.get("compatibilityEnrollment")
        if not isinstance(enrollment, dict) or enrollment.get("state") != "ACTIVE":
            continue
        active_sources += 1
        canonical_id = source.get("canonicalId", "<unknown>")
        current_versions = source.get("currentVersion")
        lkgs = source.get("lastKnownGood")
        providers = source.get("providers")
        if not isinstance(current_versions, dict) or not isinstance(lkgs, dict) or not isinstance(providers, list):
            source_mismatches.append(f"{canonical_id}: ACTIVE source version maps/providers malformed")
            continue
        for provider in providers:
            active_memberships += 1
            current = current_versions.get(provider)
            lkg = lkgs.get(provider)
            if not _sha(current) or not _sha(lkg):
                source_mismatches.append(f"{canonical_id}@{provider}: missing/invalid currentVersion or lastKnownGood")
            elif current != lkg:
                source_mismatches.append(f"{canonical_id}@{provider}: currentVersion != lastKnownGood")
    violations.extend(source_mismatches)

    required_markers = [
        "EXPECTED_OWNER_ID: '149634319'",
        '[[ "$GITHUB_ACTOR_ID" == "$EXPECTED_OWNER_ID" ]]',
        '"conclusion": "success"',
        '"path": ".github/workflows/source-lab-approve-candidate.yml"',
        'live candidateSetId changed; promotion is stale',
        'candidate is no longer waiting for approval',
        'approval evidence binding changed',
        'approved provider SHAs do not match live candidate',
        'approval sourceScope changed',
        'compatibility baseline moved',
        'source state moved',
        'active/LKG moved',
        'Refuse promotion if foundation moved after validation',
        'git -C farm fetch origin compatibility-farm-foundation',
        'git -C farm push origin HEAD:compatibility-farm-foundation',
    ]
    missing_markers = [marker for marker in required_markers if marker not in promotion_workflow]
    for marker in missing_markers:
        violations.append(f"promotion authority marker missing: {marker}")

    stale_check = promotion_workflow.find("Refuse promotion if foundation moved after validation")
    push = promotion_workflow.find("git -C farm push origin HEAD:compatibility-farm-foundation")
    _violate(violations, stale_check >= 0 and push >= 0 and stale_check < push,
             "stale Foundation check must occur before promotion push")

    if upstream_registry.get("policy", {}).get("keepLastKnownGoodOnFailure") is not True:
        violations.append("upstream policy keepLastKnownGoodOnFailure must remain true")
    if upstream_registry.get("policy", {}).get("perSourceFailSafe") is not True:
        violations.append("upstream policy perSourceFailSafe must remain true")

    return {
        "schemaVersion": 1,
        "phase": "A7_LKG_SAFETY",
        "status": "SAFE" if not violations else "UNSAFE",
        "providerCount": len(provider_names),
        "providers": provider_rows,
        "activeSourceCount": active_sources,
        "activeMembershipCount": active_memberships,
        "approvalCandidatePresent": approval_candidate_present,
        "candidateProviderCount": sum(1 for row in provider_rows if row.get("candidate")),
        "promotionAuthorityMarkersRequired": len(required_markers),
        "promotionAuthorityMarkersMissing": missing_markers,
        "violations": violations,
        "warnings": warnings,
        "mutatesFoundation": False,
        "promotionAttempted": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Source Lab Phase A7 — LKG Safety",
        "",
        f"- Status: **{report['status']}**",
        f"- Providers: {report['providerCount']}",
        f"- ACTIVE sources: {report['activeSourceCount']}",
        f"- ACTIVE memberships: {report['activeMembershipCount']}",
        f"- Candidate providers observed: {report['candidateProviderCount']}",
        f"- Live approval candidate present: {str(report['approvalCandidatePresent']).lower()}",
        f"- Promotion authority markers missing: {len(report['promotionAuthorityMarkersMissing'])}",
        "- Foundation mutation: **NO**",
        "- Promotion attempted: **NO**",
        "",
        "## Providers",
        "",
        "| Provider | Active/LKG | Candidate | Candidate current |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["providers"]:
        lines.append(
            f"| {row['provider']} | `{row.get('lastKnownGood')}` | "
            f"`{row.get('candidate') or '-'}` | `{row.get('candidateCurrent') or '-'}` |"
        )
    lines.extend(["", "## Violations", ""])
    if report["violations"]:
        lines.extend(f"- {item}" for item in report["violations"])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-registry", required=True, type=Path)
    parser.add_argument("--status", required=True, type=Path)
    parser.add_argument("--source-registry", required=True, type=Path)
    parser.add_argument("--promotion-workflow", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    try:
        report = audit_lkg_safety(
            load_json(args.upstream_registry),
            load_json(args.status),
            load_json(args.source_registry),
            args.promotion_workflow.read_text(encoding="utf-8"),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.markdown_output:
            args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
            args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "SAFE" else 1
    except (LkgSafetyError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
