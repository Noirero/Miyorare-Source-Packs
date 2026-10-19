#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HELD = "NEEDS_ATTENTION"
TERMINAL_CATEGORIES = {"PERMANENT_UPSTREAM", "AUTH_REQUIRED"}
REVIEWABLE_REASON_CLASSES = {
    "PARSER_REWRITE_REQUIRED",
    "ANTI_BOT_OR_SESSION",
    "UPSTREAM_SERVICE_FAILURE",
}

_RETRY_AUDIT_PATH = Path(__file__).resolve().with_name("source_retry_audit.py")
_RETRY_AUDIT_SPEC = importlib.util.spec_from_file_location("source_retry_audit_for_held", _RETRY_AUDIT_PATH)
if _RETRY_AUDIT_SPEC is None or _RETRY_AUDIT_SPEC.loader is None:
    raise RuntimeError("cannot load source_retry_audit.py")
_retry_audit = importlib.util.module_from_spec(_RETRY_AUDIT_SPEC)
_RETRY_AUDIT_SPEC.loader.exec_module(_retry_audit)

CATEGORY_PRIORITY = dict(_retry_audit.CATEGORY_PRIORITY)
KNOWN_CATEGORIES = set(CATEGORY_PRIORITY)


def load(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_time(value: Any) -> datetime | None:
    return _retry_audit.parse_time(value)


def registry_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _retry_audit.registry_map(registry)


def evidence_binding_status(
    source: dict[str, Any] | None,
    entry: dict[str, Any],
    baselines: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    tested = entry.get("testedVersions")
    if not isinstance(source, dict):
        return "REGISTRY_MISSING", {"testedVersions": tested, "currentBaselines": {}}
    providers = source.get("providers")
    if not isinstance(providers, list) or not providers:
        return "REGISTRY_PROVIDER_BINDING_INVALID", {"testedVersions": tested, "currentBaselines": {}}
    current = {provider: baselines.get(provider) for provider in providers}
    detail = {"testedVersions": tested, "currentBaselines": current}
    if not isinstance(tested, dict) or not tested:
        return "MISSING_TESTED_VERSIONS", detail
    if set(tested) != set(providers):
        return "PROVIDER_SET_MISMATCH", detail
    if any(not isinstance(current.get(provider), str) or len(str(current.get(provider))) != 40 for provider in providers):
        return "CURRENT_BASELINE_INVALID", detail
    if any(tested.get(provider) != current.get(provider) for provider in providers):
        return "STALE", detail
    return "CURRENT", detail


def effective_category(stored: Any, inferred: str) -> tuple[str, str, bool | None]:
    stored_value = str(stored) if isinstance(stored, str) and stored else None
    stored_known = stored_value if stored_value in KNOWN_CATEGORIES else None
    inferred_known = inferred if inferred in KNOWN_CATEGORIES else "UNKNOWN"
    if stored_known and stored_known != "UNKNOWN":
        agreement = None if inferred_known == "UNKNOWN" else stored_known == inferred_known
        return stored_known, "STORED", agreement
    return inferred_known, "INFERRED", None


def operational_reason_class(category: str, findings: list[dict[str, Any]]) -> str:
    if category == "AUTH_REQUIRED":
        return "AUTH_REQUIRED"
    if category != "PERMANENT_UPSTREAM":
        return category
    reasons = " ".join(str(item.get("reason") or "") for item in findings).lower()
    if any(token in reasons for token in ("parser is broken", "layout/api changed", "needs rewrite")):
        return "PARSER_REWRITE_REQUIRED"
    if any(token in reasons for token in ("cloudflare challenge", "captcha", "access denied", "http 403")):
        return "ANTI_BOT_OR_SESSION"
    if any(token in reasons for token in ("tls error", "origin tls", "5xx", "misconfigured")):
        return "UPSTREAM_SERVICE_FAILURE"
    if any(token in reasons for token in ("parked", "landing page only", "no manga content")):
        return "SITE_PARKED_OR_NO_CONTENT"
    if any(token in reasons for token in ("hijacked", "spam/ads", "unrelated domain", "redirects to an unrelated")):
        return "DOMAIN_HIJACKED_OR_REDIRECTED"
    if any(token in reasons for token in ("no dns", "original site closed", "site is gone", "site closed")):
        return "SITE_CLOSED_OR_GONE"
    return "PERMANENT_UPSTREAM_OTHER"


def disposition(
    category: str,
    reason_class: str,
    evidence_status: str,
    category_agreement: bool | None,
) -> str:
    if category_agreement is False:
        return "REVIEW_CATEGORY_CONFLICT"
    if evidence_status != "CURRENT":
        if category in TERMINAL_CATEGORIES:
            return "REVALIDATE_STALE_TERMINAL_EVIDENCE"
        return "REVIEW_STALE_OR_INCOMPLETE_EVIDENCE"
    if category == "AUTH_REQUIRED":
        return "KEEP_HELD_AUTH_REQUIRED"
    if category == "PERMANENT_UPSTREAM":
        if reason_class == "PARSER_REWRITE_REQUIRED":
            return "REVIEW_FIXABLE_PARSER_HOLD"
        if reason_class == "ANTI_BOT_OR_SESSION":
            return "REVIEW_ANTI_BOT_OR_SESSION_HOLD"
        if reason_class == "UPSTREAM_SERVICE_FAILURE":
            return "REVIEW_UPSTREAM_SERVICE_HOLD"
        if reason_class in {
            "SITE_CLOSED_OR_GONE",
            "SITE_PARKED_OR_NO_CONTENT",
            "DOMAIN_HIJACKED_OR_REDIRECTED",
        }:
            return "KEEP_HELD_SITE_UNAVAILABLE"
        return "KEEP_HELD_PERMANENT_UPSTREAM"
    return "REVIEW_NONTERMINAL_OR_UNKNOWN_HOLD"


def audit(registry: dict[str, Any], state: dict[str, Any], now: datetime) -> dict[str, Any]:
    state_sources = state.get("sources")
    if not isinstance(state_sources, dict):
        raise ValueError("state.sources must be an object")
    baselines = registry.get("providerBaselines")
    if not isinstance(baselines, dict):
        raise ValueError("registry.providerBaselines must be an object")
    sources = registry_map(registry)

    rows: list[dict[str, Any]] = []
    for canonical_id, raw in state_sources.items():
        if not isinstance(raw, dict) or raw.get("state") != HELD:
            continue
        source = sources.get(canonical_id)
        inferred, findings = _retry_audit.classify_entry(raw)
        category, category_source, category_agreement = effective_category(raw.get("failureCategory"), inferred)
        reason_class = operational_reason_class(category, findings)
        evidence_status, binding = evidence_binding_status(source, raw, baselines)
        checked = parse_time(raw.get("lastCheckedAt"))
        hold_reason = raw.get("holdReason") if isinstance(raw.get("holdReason"), str) else None
        metadata_complete = bool(raw.get("failureCategory") and hold_reason)
        review_disposition = disposition(category, reason_class, evidence_status, category_agreement)
        enrollment = source.get("compatibilityEnrollment") if isinstance(source, dict) else None
        enrollment_state = enrollment.get("state") if isinstance(enrollment, dict) else None
        row = {
            "canonicalId": canonical_id,
            "language": source.get("language") if isinstance(source, dict) else None,
            "providers": source.get("providers") if isinstance(source, dict) else [],
            "registryEnrollmentState": enrollment_state,
            "attempts": int(raw.get("attempts", 0) or 0),
            "lifetimeAttempts": int(raw.get("lifetimeAttempts", raw.get("attempts", 0)) or 0),
            "lastCheckedAt": raw.get("lastCheckedAt"),
            "ageHours": round((now - checked).total_seconds() / 3600, 2) if checked else None,
            "timestampValid": checked is not None,
            "workflowRunId": raw.get("workflowRunId"),
            "storedFailureCategory": raw.get("failureCategory"),
            "inferredPrimaryCategory": inferred,
            "effectiveCategory": category,
            "operationalReasonClass": reason_class,
            "categorySource": category_source,
            "categoryAgreement": category_agreement,
            "holdReason": hold_reason,
            "metadataComplete": metadata_complete,
            "ownerActionRequired": bool(raw.get("ownerActionRequired")),
            "evidenceBindingStatus": evidence_status,
            "baselineBindingStale": evidence_status == "STALE",
            "testedVersions": binding["testedVersions"],
            "currentBaselines": binding["currentBaselines"],
            "findings": findings,
            "reviewDisposition": review_disposition,
            "policyConsistentCurrentHold": (
                evidence_status == "CURRENT"
                and category in TERMINAL_CATEGORIES
                and category_agreement is not False
            ),
            "operationallyReviewableCurrentHold": (
                evidence_status == "CURRENT"
                and reason_class in REVIEWABLE_REASON_CLASSES
                and category_agreement is not False
            ),
            "reviewRequired": not review_disposition.startswith("KEEP_HELD_"),
        }
        rows.append(row)

    rows.sort(key=lambda row: (str(row["reviewDisposition"]), str(row["operationalReasonClass"]), row["canonicalId"]))
    by_category = Counter(row["effectiveCategory"] for row in rows)
    by_reason = Counter(row["operationalReasonClass"] for row in rows)
    by_disposition = Counter(row["reviewDisposition"] for row in rows)
    by_binding = Counter(row["evidenceBindingStatus"] for row in rows)
    by_language = Counter(str(row["language"] or "unknown") for row in rows)

    return {
        "schemaVersion": 1,
        "phase": "A5_HELD_OBSERVABILITY",
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "readOnly": True,
        "summary": {
            "totalHeld": len(rows),
            "byEffectiveCategory": dict(sorted(by_category.items())),
            "byOperationalReasonClass": dict(sorted(by_reason.items())),
            "byReviewDisposition": dict(sorted(by_disposition.items())),
            "byEvidenceBindingStatus": dict(sorted(by_binding.items())),
            "byLanguage": dict(sorted(by_language.items())),
            "currentEvidence": sum(1 for row in rows if row["evidenceBindingStatus"] == "CURRENT"),
            "staleEvidence": sum(1 for row in rows if row["evidenceBindingStatus"] == "STALE"),
            "incompleteOrMismatchedEvidence": sum(
                1 for row in rows if row["evidenceBindingStatus"] not in {"CURRENT", "STALE"}
            ),
            "terminalCategory": sum(1 for row in rows if row["effectiveCategory"] in TERMINAL_CATEGORIES),
            "nonterminalOrUnknownCategory": sum(1 for row in rows if row["effectiveCategory"] not in TERMINAL_CATEGORIES),
            "metadataComplete": sum(1 for row in rows if row["metadataComplete"]),
            "metadataIncomplete": sum(1 for row in rows if not row["metadataComplete"]),
            "categoryConflicts": sum(1 for row in rows if row["categoryAgreement"] is False),
            "reviewRequired": sum(1 for row in rows if row["reviewRequired"]),
            "policyConsistentCurrentHold": sum(1 for row in rows if row["policyConsistentCurrentHold"]),
            "operationallyReviewableCurrentHold": sum(1 for row in rows if row["operationallyReviewableCurrentHold"]),
            "ownerActionRequiredFlagged": sum(1 for row in rows if row["ownerActionRequired"]),
        },
        "policyObservations": {
            "automaticMutationPerformed": False,
            "heldMutationPerformed": False,
            "retryMutationPerformed": False,
            "lkgMutationPerformed": False,
            "terminalCategories": sorted(TERMINAL_CATEGORIES),
            "reviewableReasonClasses": sorted(REVIEWABLE_REASON_CLASSES),
            "operationalReasonDoesNotMutateLifecycleCategory": True,
            "reviewRowsAreObservabilityOnly": True,
            "staleHeldRowsAreReviewOnly": True,
        },
        "heldEntries": rows,
    }


def markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Source Lab Phase A5 — Held observability",
        "",
        f"Generated: `{report['generatedAt']}`",
        "",
        "This report is read-only. It does not move Held/Retry state, change provider pins, or mutate LKG.",
        "",
        "## Summary",
        "",
        f"- Total Held: **{summary['totalHeld']}**",
        f"- Current evidence: **{summary['currentEvidence']}**",
        f"- Stale evidence: **{summary['staleEvidence']}**",
        f"- Incomplete/mismatched evidence: **{summary['incompleteOrMismatchedEvidence']}**",
        f"- Lifecycle-terminal category: **{summary['terminalCategory']}**",
        f"- Operationally reviewable current Held: **{summary['operationallyReviewableCurrentHold']}**",
        f"- Review required: **{summary['reviewRequired']}**",
        f"- Legacy/incomplete metadata: **{summary['metadataIncomplete']}**",
        "",
        "## Operational reason classes",
        "",
    ]
    for name, count in summary["byOperationalReasonClass"].items():
        lines.append(f"- {name}: **{count}**")
    lines.extend([
        "",
        "## Held entries",
        "",
        "| Canonical ID | Lang | Lifecycle category | Operational reason | Evidence | Disposition | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in report["heldEntries"]:
        reason = ""
        findings = row.get("findings") if isinstance(row.get("findings"), list) else []
        if findings:
            reason = str(findings[0].get("reason") or "")
        if not reason:
            reason = str(row.get("holdReason") or "")
        reason = reason.replace("|", "\\|").replace("\n", " ")[:180]
        canonical_id = str(row["canonicalId"]).replace("|", "\\|")
        lines.append(
            f"| `{canonical_id}` | {row.get('language') or '-'} | {row['effectiveCategory']} | "
            f"{row['operationalReasonClass']} | {row['evidenceBindingStatus']} | "
            f"{row['reviewDisposition']} | {reason or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only observability report for Source Lab Held entries")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--now", required=True, help="UTC ISO-8601 timestamp used for deterministic age calculations")
    args = parser.parse_args()

    now = parse_time(args.now)
    if now is None:
        raise SystemExit("--now must be a valid ISO-8601 timestamp")
    report = audit(load(args.registry), load(args.state), now)
    save(args.output, report)
    markdown_target = Path(args.markdown_output)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
