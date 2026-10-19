#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
PROFILE = "PARSER_PENDING"
READY = "READY_FOR_APPROVAL"
RETRY = "RETRY"
HELD = "NEEDS_ATTENTION"
URL_RE = re.compile(r'https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\d+)?')
BASE_URL_RE = re.compile(r'\b(?:baseUrl|baseURL|BASE_URL)\s*(?:=|:)\s*["\']https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\d+)?', re.I)
DOMAIN_CONFIG_RE = re.compile(r'\b(?:ConfigKey\.)?Domain\s*\(\s*["\']([A-Za-z0-9.-]+\.[A-Za-z]{2,})["\']\s*\)', re.I)
PARSER_HOST_RE = re.compile(r'\b(?!MangaSourceParser\b)[A-Za-z_][A-Za-z0-9_]*Parser\s*\([^)]*?["\']([A-Za-z0-9.-]+\.[A-Za-z]{2,})["\']', re.S)
QUOTED_HOST_RE = re.compile(r'["\']([A-Za-z0-9](?:[A-Za-z0-9.-]*\.)[A-Za-z]{2,})["\']')
BROKEN_RE = re.compile(r'@Broken(?:\s*\(\s*["\']([^"\']*)["\']\s*\))?', re.I)

FAMILY_RULES = (
    ("madara", ("Madara", "MadaraFactory", "MadaraLegacy")),
    ("natsu", ("Natsu", "NatsuId")),
    ("manga-reader-plus-api", ("MangaReader", "manga-reader", "MangaReaderPlus")),
    ("custom-paged-form-api", ("FormBody", "submitForm", "POST", "post(")),
    ("custom-rest-json", ("Json", "json", "api/", "application/json")),
    ("custom-paged-html-xhr", ("XMLHttpRequest", "xhr", "X-Requested-With")),
    ("custom-paged-html", ("select(", "Document", "Element", "Jsoup")),
)

# A4 retry taxonomy. Only genuinely terminal evidence is allowed to enter Held
# automatically. Environment, harness, parser and transient failures remain
# RETRY with category-aware backoff. A provider-baseline move invalidates the
# prior retry budget and bypasses any old cooldown for one controlled recheck.
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
IMMEDIATE_HOLD_CATEGORIES = {"PERMANENT_UPSTREAM", "AUTH_REQUIRED"}
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
BACKOFF_POLICY = {
    "NETWORK_TRANSIENT": (2, 24),
    "PROFILE_TRANSIENT": (2, 24),
    "ANTI_BOT_OR_HTTP_BLOCK": (6, 24),
    "NATIVE_DEPENDENCY": (6, 24),
    "HARNESS_API_MISMATCH": (6, 24),
    "INITIALIZATION_FAILURE": (6, 24),
    "REFLECTION_WRAPPER": (6, 24),
    "PARSER_EVIDENCE_MISSING": (6, 24),
    "SOURCE_PARSER_FAILURE": (12, 72),
    "UNKNOWN": (6, 24),
}


def load(path: str | Path, *, default: Any = None) -> Any:
    target = Path(path)
    if not target.is_file() and default is not None:
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_sources(registry: dict[str, Any]) -> list[dict[str, Any]]:
    sources = registry.get("sources")
    if not isinstance(sources, list):
        raise ValueError("registry.sources must be a list")
    return sources


def normalize_state(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    # Worker schema v1 only proved compile + reachability. Those READY/HELD
    # decisions are not valid evidence for schema v2 real-parser onboarding,
    # so migrate fail-closed by re-queuing every legacy entry from scratch.
    if raw.get("schemaVersion") != 2:
        return {"schemaVersion": 2, "sources": {}}
    sources = raw.get("sources")
    if not isinstance(sources, dict):
        sources = {}
    normalized = dict(raw)
    normalized["schemaVersion"] = 2
    normalized["sources"] = sources
    return normalized


def state_entry(state: dict[str, Any], canonical_id: str) -> dict[str, Any]:
    value = state.get("sources", {}).get(canonical_id)
    return value if isinstance(value, dict) else {}


def provider_baseline_binding(
    source: dict[str, Any],
    provider_baselines: dict[str, Any],
    providers: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict[str, Any]:
    source_providers = source.get("providers")
    if not isinstance(source_providers, list) or not isinstance(provider_baselines, dict):
        return {}
    selected = list(source_providers if providers is None else providers)
    if not selected or any(provider not in source_providers for provider in selected):
        return {}
    return {provider: provider_baselines.get(provider) for provider in selected}


def _version_evidence_is_stale(
    source: dict[str, Any],
    worker_state: dict[str, Any],
    provider_baselines: dict[str, Any],
    *,
    missing_is_stale: bool,
) -> bool:
    tested = worker_state.get("testedVersions")
    if not isinstance(tested, dict) or not tested:
        return missing_is_stale
    current = provider_baseline_binding(source, provider_baselines, set(tested))
    if set(current) != set(tested):
        return True
    if any(not isinstance(value, str) or len(value) != 40 for value in current.values()):
        return missing_is_stale
    return tested != current


def ready_evidence_is_stale(
    source: dict[str, Any],
    worker_state: dict[str, Any],
    provider_baselines: dict[str, Any],
) -> bool:
    if worker_state.get("state") != READY:
        return False
    return _version_evidence_is_stale(source, worker_state, provider_baselines, missing_is_stale=True)


def held_evidence_is_stale(
    source: dict[str, Any],
    worker_state: dict[str, Any],
    provider_baselines: dict[str, Any],
) -> bool:
    if worker_state.get("state") != HELD:
        return False
    return _version_evidence_is_stale(source, worker_state, provider_baselines, missing_is_stale=False)


def retry_evidence_is_stale(
    source: dict[str, Any],
    worker_state: dict[str, Any],
    provider_baselines: dict[str, Any],
) -> bool:
    if worker_state.get("state") != RETRY:
        return False
    return _version_evidence_is_stale(source, worker_state, provider_baselines, missing_is_stale=True)


def invalidate_stale_ready(registry: dict[str, Any], state: dict[str, Any]) -> int:
    provider_baselines = registry.get("providerBaselines")
    if not isinstance(provider_baselines, dict):
        raise ValueError("registry.providerBaselines invalid")
    invalidated = 0
    for source in canonical_sources(registry):
        enrollment = source.get("compatibilityEnrollment")
        if not isinstance(enrollment, dict) or enrollment.get("state") != "PENDING":
            continue
        entry = state_entry(state, str(source.get("canonicalId", "")))
        if not ready_evidence_is_stale(source, entry, provider_baselines):
            continue
        entry["state"] = RETRY
        entry["approvalState"] = "NOT_READY"
        entry["ownerActionRequired"] = False
        entry["publishEligible"] = False
        entry["revalidationReason"] = "PROVIDER_BASELINE_CHANGED"
        invalidated += 1
    return invalidated


def invalidate_stale_held(registry: dict[str, Any], state: dict[str, Any]) -> int:
    provider_baselines = registry.get("providerBaselines")
    if not isinstance(provider_baselines, dict):
        raise ValueError("registry.providerBaselines invalid")
    invalidated = 0
    for source in canonical_sources(registry):
        enrollment = source.get("compatibilityEnrollment")
        if not isinstance(enrollment, dict) or enrollment.get("state") != "PENDING":
            continue
        entry = state_entry(state, str(source.get("canonicalId", "")))
        if not held_evidence_is_stale(source, entry, provider_baselines):
            continue
        entry["state"] = RETRY
        entry["approvalState"] = "NOT_READY"
        entry["ownerActionRequired"] = False
        entry["publishEligible"] = False
        entry["revalidationReason"] = "PROVIDER_BASELINE_CHANGED"
        invalidated += 1
    return invalidated


def eligible(
    source: dict[str, Any],
    state: dict[str, Any],
    provider_baselines: dict[str, Any],
) -> bool:
    enrollment = source.get("compatibilityEnrollment")
    if not isinstance(enrollment, dict) or enrollment.get("state") != "PENDING":
        return False
    worker_state = state_entry(state, source.get("canonicalId", ""))
    status = worker_state.get("state")
    if status in {HELD, "APPROVED"}:
        return False
    if status == READY:
        return ready_evidence_is_stale(source, worker_state, provider_baselines)
    return True


def retry_is_due(
    source: dict[str, Any],
    worker_state: dict[str, Any],
    provider_baselines: dict[str, Any],
    now: datetime,
) -> bool:
    if worker_state.get("state") != RETRY:
        return True
    # A new provider baseline is new evidence. Never let old cooldown metadata
    # block one controlled revalidation, and do not carry its attempt budget.
    if retry_evidence_is_stale(source, worker_state, provider_baselines):
        return True
    next_eligible = parse_utc(worker_state.get("nextEligibleAt"))
    return next_eligible is None or next_eligible <= now


def build_plan(
    registry: dict[str, Any],
    state: dict[str, Any],
    batch_size: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    provider_baselines = registry.get("providerBaselines")
    if not isinstance(provider_baselines, dict):
        raise ValueError("registry.providerBaselines invalid")
    invalidated_ready = invalidate_stale_ready(registry, state)
    invalidated_held = invalidate_stale_held(registry, state)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    rows: list[tuple[int, str, str, str, bool, int, int, dict[str, Any]]] = []
    deferred_retry = 0
    stale_retry_candidates = 0
    for source in canonical_sources(registry):
        if not eligible(source, state, provider_baselines):
            continue
        worker_state = state_entry(state, source["canonicalId"])
        is_retry = worker_state.get("state") == RETRY
        baseline_reset = is_retry and retry_evidence_is_stale(source, worker_state, provider_baselines)
        if is_retry and not retry_is_due(source, worker_state, provider_baselines, now):
            deferred_retry += 1
            continue
        previous_attempts = int(worker_state.get("attempts", 0) or 0)
        lifetime_attempts = int(worker_state.get("lifetimeAttempts", previous_attempts) or 0)
        effective_attempts = 0 if baseline_reset else previous_attempts
        if baseline_reset:
            stale_retry_candidates += 1
        rows.append((
            effective_attempts,
            str(worker_state.get("lastCheckedAt", "")),
            str(source.get("language", "")),
            str(source.get("canonicalId", "")),
            baseline_reset,
            previous_attempts,
            lifetime_attempts,
            source,
        ))
    rows.sort(key=lambda item: item[:4])

    retry_rows = [row for row in rows if state_entry(state, row[-1]["canonicalId"]).get("state") == RETRY]
    fresh_rows = [row for row in rows if row not in retry_rows]

    limit = max(1, batch_size)
    retry_budget = min(len(retry_rows), max(1, limit // 4))
    selected: list[dict[str, Any]] = []
    language_counts = {"id": 0, "en": 0}

    def take_balanced(
        pool: list[tuple[int, str, str, str, bool, int, int, dict[str, Any]]],
        count: int,
    ) -> None:
        remaining = list(pool)
        while remaining and len(selected) < count:
            preferred = "id" if language_counts["id"] <= language_counts["en"] else "en"
            index = next((i for i, row in enumerate(remaining) if row[-1].get("language") == preferred), 0)
            row = remaining.pop(index)
            source = row[-1]
            selected.append({
                "canonicalId": source["canonicalId"],
                "language": source["language"],
                "providers": source["providers"],
                "upstreamIdentities": source["upstreamIdentities"],
                "attempts": row[0],
                "baselineReset": row[4],
                "previousAttempts": row[5],
                "lifetimeAttempts": row[6],
            })
            language = source.get("language")
            if language in language_counts:
                language_counts[language] += 1

    take_balanced(retry_rows, retry_budget)
    take_balanced(fresh_rows, limit)
    if len(selected) < limit:
        selected_ids = {item["canonicalId"] for item in selected}
        remaining_retries = [row for row in retry_rows if row[-1]["canonicalId"] not in selected_ids]
        take_balanced(remaining_retries, limit)

    return {
        "schemaVersion": 2,
        "batchSize": len(selected),
        "retrySlots": sum(1 for item in selected if state_entry(state, item["canonicalId"]).get("state") == RETRY),
        "deferredRetry": deferred_retry,
        "staleRetryResetCandidates": stale_retry_candidates,
        "invalidatedReady": invalidated_ready,
        "invalidatedHeld": invalidated_held,
        "items": selected,
    }


def read_provider_text(provider: str, identity: dict[str, Any], root: Path) -> tuple[bool, str, str]:
    locator = identity.get("module") if provider == "keiyoushi" else identity.get("file")
    if not isinstance(locator, str) or not locator:
        return False, "", "missing-locator"
    target = root / locator
    if provider == "keiyoushi":
        if not target.is_dir():
            return False, "", locator
        files = list(target.rglob("*.kt")) + [target / "build.gradle.kts"]
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in files if path.is_file())
        return bool(text.strip()), text, locator
    if not target.is_file():
        return False, "", locator
    return True, target.read_text(encoding="utf-8", errors="ignore"), locator


def infer_family(text: str, provider: str) -> str:
    for family, tokens in FAMILY_RULES:
        if any(token in text for token in tokens):
            return family
    return f"{provider}-native"


def infer_auth(text: str) -> str:
    lowered = text.lower()
    if "password" in lowered and ("login" in lowered or "signin" in lowered):
        return "FORM"
    if "set-cookie" in lowered or "login_cookie" in lowered or "auth_cookie" in lowered:
        return "COOKIE"
    if "bearer " in lowered or 'header("authorization"' in lowered or "header('authorization'" in lowered:
        return "TOKEN"
    return "NO_AUTH"


def infer_host(text: str) -> str | None:
    for pattern in (BASE_URL_RE, URL_RE, DOMAIN_CONFIG_RE, PARSER_HOST_RE):
        match = pattern.search(text)
        if match:
            return match.group(1).lower().rstrip(".")
    quoted = QUOTED_HOST_RE.findall(text)
    return quoted[-1].lower().rstrip(".") if quoted else None


def infer_broken_reason(text: str) -> str | None:
    match = BROKEN_RE.search(text)
    if not match:
        return None
    reason = (match.group(1) or "").strip()
    return reason or "upstream-declared-broken"


def http_probe(host: str, timeout: float) -> dict[str, Any]:
    url = f"https://{host}/"
    request = urllib.request.Request(url, headers={"User-Agent": "Miyorare-Compatibility-Farm/1.0", "Accept": "text/html,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            response.read(512)
            return {"reachable": status < 500, "httpStatus": status, "url": url}
    except urllib.error.HTTPError as exc:
        return {"reachable": int(exc.code) < 500, "httpStatus": int(exc.code), "url": url, "detail": f"http-{exc.code}"}
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return {"reachable": False, "url": url, "detail": type(exc).__name__}


def evidence_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _auth_type(values: list[str]) -> str:
    return "FORM" if "FORM" in values else "TOKEN" if "TOKEN" in values else "COOKIE" if "COOKIE" in values else "NO_AUTH"


def _text_blob(*values: Any) -> str:
    return " ".join(str(value) for value in values if value is not None).lower()


def classify_profile_membership(member: dict[str, Any]) -> str:
    broken = member.get("upstreamBrokenReason")
    if isinstance(broken, str) and broken.strip():
        return "PERMANENT_UPSTREAM"
    probe = member.get("probe") if isinstance(member.get("probe"), dict) else {}
    blob = _text_blob(probe.get("detail"), probe.get("httpStatus"))
    if probe.get("httpStatus") == 403 or any(token in blob for token in ANTI_BOT_TEXT):
        return "ANTI_BOT_OR_HTTP_BLOCK"
    if any(token in blob for token in NETWORK_TEXT) or str(probe.get("detail") or "") in {
        "URLError", "TimeoutError", "socket.timeout", "gaierror", "ConnectionError"
    }:
        return "NETWORK_TRANSIENT"
    if member.get("profilePass") is not True:
        return "PROFILE_TRANSIENT"
    return "UNKNOWN"


def classify_parser_membership(member: dict[str, Any]) -> str:
    reason = str(member.get("reason") or "")
    failure_type = str(member.get("failureType") or "")
    failure_message = str(member.get("failureMessage") or "")
    blob = _text_blob(reason, failure_type, failure_message)
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


def primary_category(categories: list[str]) -> str:
    return max(categories, key=lambda value: CATEGORY_PRIORITY.get(value, 0)) if categories else "UNKNOWN"


def retry_backoff_hours(category: str, attempts: int) -> int:
    base, maximum = BACKOFF_POLICY.get(category, BACKOFF_POLICY["UNKNOWN"])
    exponent = max(0, min(max(1, attempts) - 1, 6))
    return min(base * (2 ** exponent), maximum)


def assess_plan(plan: dict[str, Any], roots: dict[str, Path], compile_results: dict[str, Any], timeout: float, fail_threshold: int) -> dict[str, Any]:
    # fail_threshold remains accepted for backward-compatible workflow/API
    # contracts, but A4 no longer turns non-terminal failures into Held solely
    # because an attempt counter reached this generic threshold.
    _ = fail_threshold
    results: list[dict[str, Any]] = []
    for item in plan.get("items", []):
        memberships: list[dict[str, Any]] = []
        passing_families: list[str] = []
        passing_auth_types: list[str] = []
        failures: list[dict[str, Any]] = []
        selected_providers: list[str] = []
        for provider in item["providers"]:
            identity = item["upstreamIdentities"].get(provider, {})
            exists, text, locator = read_provider_text(provider, identity, roots[provider])
            family = infer_family(text, provider) if exists else None
            auth_type = infer_auth(text) if exists else "UNSUPPORTED"
            host = infer_host(text) if exists else None
            broken_reason = infer_broken_reason(text) if exists else None
            provider_compile = compile_results.get(provider, {})
            compile_ok = bool(provider_compile.get(locator, provider_compile.get("*", False)))
            probe = (
                {"reachable": False, "detail": "upstream-declared-broken"}
                if broken_reason
                else ({"reachable": False, "detail": "no-probe-host"} if not host else http_probe(host, timeout))
            )
            passed = exists and compile_ok and broken_reason is None and probe.get("reachable") is True
            if passed:
                selected_providers.append(provider)
                if family:
                    passing_families.append(family)
                if auth_type != "UNSUPPORTED":
                    passing_auth_types.append(auth_type)
            else:
                failures.append({
                    "provider": provider,
                    "locator": locator,
                    "exists": exists,
                    "compile": compile_ok,
                    "probe": probe,
                    "hardFailure": broken_reason is not None,
                    "reason": broken_reason,
                })
            memberships.append({
                "provider": provider,
                "locator": locator,
                "exists": exists,
                "compile": compile_ok,
                "family": family,
                "authType": auth_type,
                "probeHost": host,
                "probe": probe,
                "upstreamBrokenReason": broken_reason,
                "profilePass": passed,
            })
        attempts = int(item.get("attempts", 0) or 0) + 1
        lifetime_attempts = int(item.get("lifetimeAttempts", item.get("previousAttempts", item.get("attempts", 0))) or 0) + 1
        failed_categories = [classify_profile_membership(member) for member in memberships if member.get("profilePass") is not True]
        failure_category = primary_category(failed_categories)
        hard_failure = failure_category in IMMEDIATE_HOLD_CATEGORIES
        outcome = PROFILE if selected_providers else (HELD if hard_failure else RETRY)
        family = (
            passing_families[0]
            if passing_families and all(value == passing_families[0] for value in passing_families)
            else ("multi-provider" if passing_families else "unclassified")
        )
        auth_type = _auth_type(passing_auth_types)
        profile_gate = "PASS" if selected_providers else "FAIL"
        evidence = {
            "profile": {
                "memberships": memberships,
                "gate": profile_gate,
                "selectedProviders": sorted(selected_providers),
                "heldProviders": sorted(
                    member["provider"] for member in memberships if member.get("profilePass") is not True
                ),
            },
            "attempts": attempts,
        }
        results.append({
            "canonicalId": item["canonicalId"],
            "state": outcome,
            "attempts": attempts,
            "lifetimeAttempts": lifetime_attempts,
            "baselineReset": bool(item.get("baselineReset")),
            "failureCategory": failure_category if outcome != PROFILE else None,
            "adapterFamily": family,
            "authType": auth_type,
            "selectedProviders": sorted(selected_providers),
            "evidence": evidence,
            "evidenceSha256": evidence_digest(evidence),
        })
    return {"schemaVersion": 2, "results": results}


def _parser_passed(result: dict[str, Any]) -> bool:
    return (
        result.get("status") == "PASS"
        and result.get("parserExecution") is True
        and result.get("detailsTraversal") is True
        and result.get("chapterTraversal") is True
        and result.get("pageExtraction") is True
    )


def finalize_results(profile_results: dict[str, Any], parser_results: dict[str, Any], fail_threshold: int) -> dict[str, Any]:
    _ = fail_threshold
    parser_map = {
        (row.get("canonicalId"), row.get("provider")): row
        for row in parser_results.get("results", [])
        if isinstance(row, dict)
    }
    finalized: list[dict[str, Any]] = []
    for profile in profile_results.get("results", []):
        row = dict(profile)
        if row.get("state") != PROFILE:
            finalized.append(row)
            continue
        memberships = row.get("evidence", {}).get("profile", {}).get("memberships", [])
        expected = [
            member.get("provider")
            for member in memberships
            if isinstance(member, dict) and member.get("profilePass") is True
        ]
        parser_evidence: list[dict[str, Any]] = []
        passed_providers: list[str] = []
        for provider in expected:
            result = parser_map.get((row.get("canonicalId"), provider))
            if result is None:
                result = {
                    "canonicalId": row.get("canonicalId"),
                    "provider": provider,
                    "status": "FAIL",
                    "parserExecution": False,
                    "reason": "PARSER_EVIDENCE_MISSING",
                }
            parser_evidence.append(result)
            if _parser_passed(result):
                passed_providers.append(provider)
        attempts = int(row.get("attempts", 0) or 0)
        failed_categories = [classify_parser_membership(item) for item in parser_evidence if not _parser_passed(item)]
        failure_category = primary_category(failed_categories)
        hard_parser_failure = failure_category in IMMEDIATE_HOLD_CATEGORIES
        has_pass = bool(passed_providers)
        outcome = READY if has_pass else (HELD if hard_parser_failure else RETRY)
        evidence = dict(row.get("evidence", {}))
        evidence["parser"] = {
            "executionMode": parser_results.get("executionMode", "real-live-parser"),
            "memberships": parser_evidence,
            "gate": "PASS" if has_pass else "FAIL",
            "selectedProviders": sorted(passed_providers),
            "heldProviders": sorted(provider for provider in expected if provider not in passed_providers),
        }
        evidence["gate"] = "REAL_PARSER_PASS" if has_pass else "REAL_PARSER_BLOCKED"
        selected_profile_members = [
            member
            for member in memberships
            if isinstance(member, dict) and member.get("provider") in passed_providers
        ]
        selected_families = [
            str(member["family"])
            for member in selected_profile_members
            if isinstance(member.get("family"), str) and member.get("family")
        ]
        selected_auth_types = [
            str(member["authType"])
            for member in selected_profile_members
            if isinstance(member.get("authType"), str) and member.get("authType") != "UNSUPPORTED"
        ]
        if has_pass:
            row["adapterFamily"] = (
                selected_families[0]
                if selected_families and all(value == selected_families[0] for value in selected_families)
                else ("multi-provider" if selected_families else "unclassified")
            )
            row["authType"] = _auth_type(selected_auth_types)
        row["state"] = outcome
        row["failureCategory"] = None if has_pass else failure_category
        row["selectedProviders"] = sorted(passed_providers)
        row["evidence"] = evidence
        row["evidenceSha256"] = evidence_digest(evidence)
        finalized.append(row)
    return {"schemaVersion": 2, "results": finalized}


def apply_results(registry: dict[str, Any], worker_state: dict[str, Any], results: dict[str, Any], workflow_run_id: str, checked_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    pending_sources = {
        source["canonicalId"]: source
        for source in canonical_sources(registry)
        if source.get("compatibilityEnrollment", {}).get("state") == "PENDING"
    }
    valid_ids = set(pending_sources)
    state = normalize_state(worker_state)
    provider_baselines = registry.get("providerBaselines")
    if not isinstance(provider_baselines, dict):
        raise ValueError("registry.providerBaselines invalid")
    checked_time = parse_utc(checked_at)
    if checked_time is None:
        raise ValueError("checked_at must be a valid ISO-8601 timestamp")
    summary = {READY: 0, RETRY: 0, HELD: 0, PROFILE: 0}
    for result in results.get("results", []):
        canonical_id = result.get("canonicalId")
        if canonical_id not in valid_ids:
            raise ValueError(f"{canonical_id} is not a current PENDING registry member")
        source = pending_sources[canonical_id]
        outcome = result["state"]
        summary[outcome] = summary.get(outcome, 0) + 1
        if outcome == READY:
            selected_providers = result.get("selectedProviders")
            if selected_providers is None:
                selected_providers = source.get("providers")
        else:
            selected_providers = source.get("providers")
        if not isinstance(selected_providers, list) or not selected_providers:
            raise ValueError(f"{canonical_id} has no provider binding for {outcome}")
        tested_versions = provider_baseline_binding(source, provider_baselines, selected_providers)
        if set(tested_versions) != set(selected_providers) or any(
            not isinstance(value, str) or len(value) != 40 for value in tested_versions.values()
        ):
            raise ValueError(f"{canonical_id} has invalid provider baseline binding")
        entry = {
            "schemaVersion": 2,
            "state": outcome,
            "attempts": result["attempts"],
            "lifetimeAttempts": int(result.get("lifetimeAttempts", result["attempts"]) or 0),
            "lastCheckedAt": checked_at,
            "workflowRunId": str(workflow_run_id),
            "evidenceSha256": result["evidenceSha256"],
            "testedVersions": tested_versions,
            "selectedProviders": sorted(selected_providers) if outcome == READY else [],
            "adapterFamily": result["adapterFamily"],
            "authType": result["authType"],
            "approvalState": "WAITING_FOR_APPROVAL" if outcome == READY else "NOT_READY",
            "ownerActionRequired": False,
            "publishEligible": False,
            "evidence": result["evidence"],
        }
        category = str(result.get("failureCategory") or "UNKNOWN")
        if outcome == RETRY:
            applied_hours = retry_backoff_hours(category, int(result.get("attempts", 1) or 1))
            baseline_reset = bool(result.get("baselineReset"))
            entry.update({
                "failureCategory": category,
                "nextEligibleAt": format_utc(checked_time + timedelta(hours=applied_hours)),
                "retryPolicy": {
                    "version": 1,
                    "mode": "CATEGORY_BACKOFF",
                    "baseHours": BACKOFF_POLICY.get(category, BACKOFF_POLICY["UNKNOWN"])[0],
                    "maxHours": BACKOFF_POLICY.get(category, BACKOFF_POLICY["UNKNOWN"])[1],
                    "appliedHours": applied_hours,
                    "baselineReset": baseline_reset,
                    "genericFailThresholdAutoHold": False,
                },
            })
            if baseline_reset:
                entry["revalidationReason"] = "PROVIDER_BASELINE_CHANGED"
        elif outcome == HELD:
            entry["failureCategory"] = category
            entry["holdReason"] = "TERMINAL_EVIDENCE" if category in IMMEDIATE_HOLD_CATEGORIES else "EXPLICIT_HOLD"
        state["sources"][canonical_id] = entry
    state["updatedAt"] = checked_at
    state["lastWorkflowRunId"] = str(workflow_run_id)
    return state, {
        "schemaVersion": 2,
        "processed": sum(summary.values()),
        "states": summary,
        "remainingPending": sum(
            1
            for source in canonical_sources(registry)
            if source.get("compatibilityEnrollment", {}).get("state") == "PENDING"
            and eligible(source, state, provider_baselines)
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--registry", required=True)
    plan_parser.add_argument("--state", required=True)
    plan_parser.add_argument("--batch-size", type=int, default=8)
    plan_parser.add_argument("--output", required=True)
    assess_parser = sub.add_parser("assess")
    assess_parser.add_argument("--plan", required=True)
    for provider in PROVIDERS:
        assess_parser.add_argument(f"--{provider}-root", required=True)
    assess_parser.add_argument("--compile-results", required=True)
    assess_parser.add_argument("--timeout", type=float, default=8.0)
    assess_parser.add_argument("--fail-threshold", type=int, default=3)
    assess_parser.add_argument("--output", required=True)
    finalize_parser = sub.add_parser("finalize")
    finalize_parser.add_argument("--profile-results", required=True)
    finalize_parser.add_argument("--parser-results", required=True)
    finalize_parser.add_argument("--fail-threshold", type=int, default=3)
    finalize_parser.add_argument("--output", required=True)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--registry", required=True)
    apply_parser.add_argument("--state", required=True)
    apply_parser.add_argument("--results", required=True)
    apply_parser.add_argument("--workflow-run-id", required=True)
    apply_parser.add_argument("--checked-at", required=True)
    apply_parser.add_argument("--summary", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        registry = load(args.registry)
        state = normalize_state(load(args.state, default={}))
        plan = build_plan(registry, state, args.batch_size)
        save(args.state, state)
        save(args.output, plan)
    elif args.command == "assess":
        roots = {provider: Path(getattr(args, f"{provider}_root")).resolve() for provider in PROVIDERS}
        save(args.output, assess_plan(load(args.plan), roots, load(args.compile_results), args.timeout, max(1, args.fail_threshold)))
    elif args.command == "finalize":
        save(args.output, finalize_results(load(args.profile_results), load(args.parser_results), max(1, args.fail_threshold)))
    elif args.command == "apply":
        registry = load(args.registry)
        state, summary = apply_results(
            registry,
            normalize_state(load(args.state, default={})),
            load(args.results),
            args.workflow_run_id,
            args.checked_at,
        )
        save(args.state, state)
        save(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
