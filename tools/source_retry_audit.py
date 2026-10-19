#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RETRY = "RETRY"
BACKOFF_FIELDS = ("nextEligibleAt", "retryAfter", "backoffUntil")
NETWORK_TYPES = (
    "UnknownHostException",
    "SocketTimeoutException",
    "ConnectException",
    "SocketException",
    "SSLException",
    "TimeoutException",
)
NETWORK_TEXT = (
    "timed out",
    "timeout",
    "temporary failure in name resolution",
    "name or service not known",
    "connection reset",
    "connection refused",
)
HARNESS_TEXT = (
    "method mangadetailsrequest not found",
    "method chapterlistrequest not found",
    "method pagelistrequest not found",
    "nosuchmethoderror",
    "nosuchmethodexception",
    "keiyoushi.source.generated",
)
NATIVE_TEXT = ("unsatisfiedlinkerror", "java.library.path", "zstd-kmp", "jni")
INIT_TEXT = ("exceptionininitializererror", "noclassdeffounderror", "could not initialize class")
REFLECTION_TEXT = ("invocationtargetexception",)
ANTI_BOT_TEXT = ("http 403", "http-403", "cloudflare", "captcha", "access denied")

CATEGORY_PRIORITY = {
    "PERMANENT_UPSTREAM": 100,
    "AUTH_REQUIRED": 95,
    "NATIVE_DEPENDENCY": 90,
    "HARNESS_API_MISMATCH": 85,
    "INITIALIZATION_FAILURE": 80,
    "REFLECTION_WRAPPER": 75,
    "ANTI_BOT_OR_HTTP_BLOCK": 70,
    "NETWORK_TRANSIENT": 65,
    "SOURCE_PARSER_FAILURE": 60,
    "PROFILE_TRANSIENT": 55,
    "PARSER_EVIDENCE_MISSING": 50,
    "UNKNOWN": 0,
}

DISPOSITIONS = {
    "PERMANENT_UPSTREAM": "HOLD_CANDIDATE",
    "AUTH_REQUIRED": "HOLD_CANDIDATE",
    "NATIVE_DEPENDENCY": "RETRY_AFTER_ENV_FIX",
    "HARNESS_API_MISMATCH": "RETRY_AFTER_HARNESS_FIX",
    "INITIALIZATION_FAILURE": "NEEDS_HARNESS_OR_SOURCE_REVIEW",
    "REFLECTION_WRAPPER": "NEEDS_ROOT_CAUSE_UNWRAP",
    "ANTI_BOT_OR_HTTP_BLOCK": "NEEDS_SOURCE_OR_SESSION_REVIEW",
    "NETWORK_TRANSIENT": "RETRY_WITH_BACKOFF",
    "SOURCE_PARSER_FAILURE": "SOURCE_FIX_REQUIRED",
    "PROFILE_TRANSIENT": "RETRY_WITH_BACKOFF",
    "PARSER_EVIDENCE_MISSING": "NEEDS_EVIDENCE_REPAIR",
    "UNKNOWN": "NEEDS_REVIEW",
}


def load(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def text_blob(*values: Any) -> str:
    return " ".join(str(value) for value in values if value is not None).lower()


def classify_parser_membership(member: dict[str, Any]) -> str:
    reason = str(member.get("reason") or "")
    failure_type = str(member.get("failureType") or "")
    failure_message = str(member.get("failureMessage") or "")
    blob = text_blob(reason, failure_type, failure_message)

    if reason.startswith("AUTH_REQUIRED:"):
        return "AUTH_REQUIRED"
    if any(token in blob for token in NATIVE_TEXT):
        return "NATIVE_DEPENDENCY"
    if any(token in blob for token in HARNESS_TEXT):
        return "HARNESS_API_MISMATCH"
    if any(token in blob for token in INIT_TEXT):
        return "INITIALIZATION_FAILURE"
    if any(token in blob for token in REFLECTION_TEXT):
        return "REFLECTION_WRAPPER"
    if any(token.lower() in blob for token in NETWORK_TYPES) or any(token in blob for token in NETWORK_TEXT):
        return "NETWORK_TRANSIENT"
    if any(token in blob for token in ANTI_BOT_TEXT):
        return "ANTI_BOT_OR_HTTP_BLOCK"
    if reason == "PARSER_EVIDENCE_MISSING" or member.get("parserExecution") is False:
        return "PARSER_EVIDENCE_MISSING"
    if member.get("status") == "FAIL" or int(member.get("failures", 0) or 0) > 0 or int(member.get("errors", 0) or 0) > 0:
        return "SOURCE_PARSER_FAILURE"
    return "UNKNOWN"


def classify_profile_membership(member: dict[str, Any]) -> str:
    broken = member.get("upstreamBrokenReason")
    if isinstance(broken, str) and broken.strip():
        return "PERMANENT_UPSTREAM"
    probe = member.get("probe") if isinstance(member.get("probe"), dict) else {}
    blob = text_blob(probe.get("detail"), probe.get("httpStatus"))
    if any(token in blob for token in ANTI_BOT_TEXT) or probe.get("httpStatus") == 403:
        return "ANTI_BOT_OR_HTTP_BLOCK"
    if any(token in blob for token in NETWORK_TEXT) or str(probe.get("detail") or "") in {
        "URLError", "TimeoutError", "socket.timeout", "gaierror", "ConnectionError"
    }:
        return "NETWORK_TRANSIENT"
    if member.get("profilePass") is not True:
        return "PROFILE_TRANSIENT"
    return "UNKNOWN"


def classify_entry(entry: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
    findings: list[dict[str, Any]] = []

    profile = evidence.get("profile") if isinstance(evidence.get("profile"), dict) else {}
    for member in profile.get("memberships", []) if isinstance(profile.get("memberships"), list) else []:
        if not isinstance(member, dict) or member.get("profilePass") is True:
            continue
        findings.append({
            "provider": member.get("provider"),
            "layer": "profile",
            "category": classify_profile_membership(member),
            "reason": member.get("upstreamBrokenReason") or (member.get("probe") or {}).get("detail"),
        })

    parser = evidence.get("parser") if isinstance(evidence.get("parser"), dict) else {}
    for member in parser.get("memberships", []) if isinstance(parser.get("memberships"), list) else []:
        if not isinstance(member, dict) or member.get("status") == "PASS":
            continue
        findings.append({
            "provider": member.get("provider"),
            "layer": "parser",
            "category": classify_parser_membership(member),
            "reason": member.get("reason") or member.get("failureMessage") or member.get("failureType"),
        })

    categories = [item["category"] for item in findings]
    primary = max(categories, key=lambda value: CATEGORY_PRIORITY.get(value, 0)) if categories else "UNKNOWN"
    return primary, findings


def registry_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = registry.get("sources")
    if not isinstance(rows, list):
        raise ValueError("registry.sources must be a list")
    return {
        str(row.get("canonicalId")): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("canonicalId"), str)
    }


def baseline_binding_stale(source: dict[str, Any] | None, entry: dict[str, Any], baselines: dict[str, Any]) -> bool:
    if not isinstance(source, dict):
        return True
    tested = entry.get("testedVersions")
    if not isinstance(tested, dict) or not tested:
        return True
    providers = source.get("providers")
    if not isinstance(providers, list):
        return True
    if set(tested) != set(providers):
        return True
    return any(tested.get(provider) != baselines.get(provider) for provider in providers)


def audit(registry: dict[str, Any], state: dict[str, Any], now: datetime, fail_threshold: int) -> dict[str, Any]:
    sources = state.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("state.sources must be an object")
    baselines = registry.get("providerBaselines")
    if not isinstance(baselines, dict):
        raise ValueError("registry.providerBaselines must be an object")
    source_map = registry_map(registry)

    rows: list[dict[str, Any]] = []
    for canonical_id, raw in sources.items():
        if not isinstance(raw, dict) or raw.get("state") != RETRY:
            continue
        primary, findings = classify_entry(raw)
        checked = parse_time(raw.get("lastCheckedAt"))
        attempts = int(raw.get("attempts", 0) or 0)
        backoff_fields = {field: raw.get(field) for field in BACKOFF_FIELDS if raw.get(field) not in (None, "")}
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
        evidence_attempts = evidence.get("attempts")
        rows.append({
            "canonicalId": canonical_id,
            "attempts": attempts,
            "atOrAboveFailThreshold": attempts >= fail_threshold,
            "lastCheckedAt": raw.get("lastCheckedAt"),
            "ageHours": round((now - checked).total_seconds() / 3600, 2) if checked else None,
            "workflowRunId": raw.get("workflowRunId"),
            "primaryCategory": primary,
            "recommendedDisposition": DISPOSITIONS[primary],
            "findings": findings,
            "backoffMetadata": backoff_fields,
            "backoffMetadataPresent": bool(backoff_fields),
            "baselineBindingStale": baseline_binding_stale(source_map.get(canonical_id), raw, baselines),
            "timestampValid": checked is not None,
            "attemptEvidenceConsistent": evidence_attempts in (None, attempts),
            "permanentHoldCandidate": primary in {"PERMANENT_UPSTREAM", "AUTH_REQUIRED"},
        })

    rows.sort(key=lambda item: item["canonicalId"])
    categories = Counter(row["primaryCategory"] for row in rows)
    dispositions = Counter(row["recommendedDisposition"] for row in rows)
    attempts = Counter(str(row["attempts"]) for row in rows)
    total = len(rows)
    with_backoff = sum(1 for row in rows if row["backoffMetadataPresent"])

    return {
        "schemaVersion": 1,
        "phase": "A4_RETRY_AUDIT",
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "readOnly": True,
        "configuredFailThreshold": fail_threshold,
        "summary": {
            "totalRetry": total,
            "byPrimaryCategory": dict(sorted(categories.items())),
            "byRecommendedDisposition": dict(sorted(dispositions.items())),
            "attemptsDistribution": dict(sorted(attempts.items(), key=lambda item: int(item[0]))),
            "atOrAboveFailThreshold": sum(1 for row in rows if row["atOrAboveFailThreshold"]),
            "withBackoffMetadata": with_backoff,
            "withoutBackoffMetadata": total - with_backoff,
            "baselineBindingStale": sum(1 for row in rows if row["baselineBindingStale"]),
            "invalidOrMissingTimestamp": sum(1 for row in rows if not row["timestampValid"]),
            "attemptEvidenceMismatch": sum(1 for row in rows if not row["attemptEvidenceConsistent"]),
            "permanentHoldCandidates": sum(1 for row in rows if row["permanentHoldCandidate"]),
        },
        "policyObservations": {
            "backoffMetadataFieldsAudited": list(BACKOFF_FIELDS),
            "noStateMutationPerformed": True,
            "retryLimitMutationPerformed": False,
            "heldMutationPerformed": False,
        },
        "retryEntries": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of Source Lab RETRY lifecycle evidence")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--fail-threshold", type=int, default=3)
    parser.add_argument("--now", required=True, help="UTC ISO-8601 timestamp used for deterministic age calculations")
    args = parser.parse_args()

    now = parse_time(args.now)
    if now is None:
        raise SystemExit("--now must be a valid ISO-8601 timestamp")
    report = audit(load(args.registry), load(args.state), now, max(1, args.fail_threshold))
    save(args.output, report)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
