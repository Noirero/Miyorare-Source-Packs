#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import urllib.error
import urllib.request
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


def load(path: str | Path, *, default: Any = None) -> Any:
    target = Path(path)
    if not target.is_file() and default is not None:
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    return {"schemaVersion": 2, "sources": sources}


def state_entry(state: dict[str, Any], canonical_id: str) -> dict[str, Any]:
    value = state.get("sources", {}).get(canonical_id)
    return value if isinstance(value, dict) else {}


def eligible(source: dict[str, Any], state: dict[str, Any]) -> bool:
    enrollment = source.get("compatibilityEnrollment")
    if not isinstance(enrollment, dict) or enrollment.get("state") != "PENDING":
        return False
    worker_state = state_entry(state, source.get("canonicalId", ""))
    return worker_state.get("state") not in {READY, HELD, "APPROVED"}


def build_plan(registry: dict[str, Any], state: dict[str, Any], batch_size: int) -> dict[str, Any]:
    rows: list[tuple[int, str, str, str, dict[str, Any]]] = []
    for source in canonical_sources(registry):
        if not eligible(source, state):
            continue
        worker_state = state_entry(state, source["canonicalId"])
        rows.append((
            int(worker_state.get("attempts", 0) or 0),
            str(worker_state.get("lastCheckedAt", "")),
            str(source.get("language", "")),
            str(source.get("canonicalId", "")),
            source,
        ))
    rows.sort(key=lambda item: item[:4])

    retry_rows = [
        row for row in rows
        if state_entry(state, row[-1]["canonicalId"]).get("state") == RETRY
    ]
    fresh_rows = [
        row for row in rows
        if state_entry(state, row[-1]["canonicalId"]).get("state") != RETRY
    ]

    limit = max(1, batch_size)
    retry_budget = min(len(retry_rows), max(1, limit // 4))
    selected: list[dict[str, Any]] = []
    language_counts = {"id": 0, "en": 0}

    def take_balanced(pool: list[tuple[int, str, str, str, dict[str, Any]]], count: int) -> None:
        remaining = list(pool)
        while remaining and len(selected) < count:
            preferred = "id" if language_counts["id"] <= language_counts["en"] else "en"
            index = next((i for i, row in enumerate(remaining) if row[-1].get("language") == preferred), 0)
            source = remaining.pop(index)[-1]
            worker_state = state_entry(state, source["canonicalId"])
            selected.append({
                "canonicalId": source["canonicalId"],
                "language": source["language"],
                "providers": source["providers"],
                "upstreamIdentities": source["upstreamIdentities"],
                "attempts": int(worker_state.get("attempts", 0) or 0),
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


def assess_plan(plan: dict[str, Any], roots: dict[str, Path], compile_results: dict[str, Any], timeout: float, fail_threshold: int) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for item in plan.get("items", []):
        memberships: list[dict[str, Any]] = []
        families: list[str] = []
        auth_types: list[str] = []
        failures: list[dict[str, Any]] = []
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
            if not passed:
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
            if family:
                families.append(family)
            if auth_type != "UNSUPPORTED":
                auth_types.append(auth_type)
        attempts = int(item.get("attempts", 0) or 0) + 1
        hard_failure = any(failure.get("hardFailure") is True for failure in failures)
        outcome = PROFILE if not failures else (HELD if hard_failure or attempts >= fail_threshold else RETRY)
        family = families[0] if families and all(value == families[0] for value in families) else ("multi-provider" if families else "unclassified")
        auth_type = "FORM" if "FORM" in auth_types else "TOKEN" if "TOKEN" in auth_types else "COOKIE" if "COOKIE" in auth_types else "NO_AUTH"
        evidence = {"profile": {"memberships": memberships, "gate": "PASS" if outcome == PROFILE else "FAIL"}, "attempts": attempts}
        results.append({"canonicalId": item["canonicalId"], "state": outcome, "attempts": attempts, "adapterFamily": family, "authType": auth_type, "evidence": evidence, "evidenceSha256": evidence_digest(evidence)})
    return {"schemaVersion": 2, "results": results}


def finalize_results(profile_results: dict[str, Any], parser_results: dict[str, Any], fail_threshold: int) -> dict[str, Any]:
    parser_map = {(row.get("canonicalId"), row.get("provider")): row for row in parser_results.get("results", []) if isinstance(row, dict)}
    finalized: list[dict[str, Any]] = []
    for profile in profile_results.get("results", []):
        row = dict(profile)
        if row.get("state") != PROFILE:
            finalized.append(row)
            continue
        memberships = row.get("evidence", {}).get("profile", {}).get("memberships", [])
        expected = [member.get("provider") for member in memberships if isinstance(member, dict) and member.get("profilePass") is True]
        parser_evidence: list[dict[str, Any]] = []
        all_pass = bool(expected)
        for provider in expected:
            result = parser_map.get((row.get("canonicalId"), provider))
            if result is None:
                result = {"canonicalId": row.get("canonicalId"), "provider": provider, "status": "FAIL", "parserExecution": False, "reason": "PARSER_EVIDENCE_MISSING"}
            parser_evidence.append(result)
            passed = result.get("status") == "PASS" and result.get("parserExecution") is True and result.get("detailsTraversal") is True and result.get("chapterTraversal") is True and result.get("pageExtraction") is True
            all_pass = all_pass and passed
        attempts = int(row.get("attempts", 0) or 0)
        outcome = READY if all_pass else (HELD if attempts >= fail_threshold else RETRY)
        evidence = dict(row.get("evidence", {}))
        evidence["parser"] = {"executionMode": parser_results.get("executionMode", "real-live-parser"), "memberships": parser_evidence, "gate": "PASS" if all_pass else "FAIL"}
        evidence["gate"] = "REAL_PARSER_PASS" if all_pass else "REAL_PARSER_BLOCKED"
        row["state"] = outcome
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
    summary = {READY: 0, RETRY: 0, HELD: 0, PROFILE: 0}
    for result in results.get("results", []):
        canonical_id = result.get("canonicalId")
        if canonical_id not in valid_ids:
            raise ValueError(f"{canonical_id} is not a current PENDING registry member")
        source = pending_sources[canonical_id]
        outcome = result["state"]
        summary[outcome] = summary.get(outcome, 0) + 1
        tested_versions = {
            provider: source.get("currentVersion", {}).get(provider)
            for provider in source.get("providers", [])
        }
        if any(not isinstance(value, str) or len(value) != 40 for value in tested_versions.values()):
            raise ValueError(f"{canonical_id} has invalid provider version binding")
        state["sources"][canonical_id] = {"schemaVersion": 2, "state": outcome, "attempts": result["attempts"], "lastCheckedAt": checked_at, "workflowRunId": str(workflow_run_id), "evidenceSha256": result["evidenceSha256"], "testedVersions": tested_versions, "adapterFamily": result["adapterFamily"], "authType": result["authType"], "approvalState": "WAITING_FOR_APPROVAL" if outcome == READY else "NOT_READY", "ownerActionRequired": False, "publishEligible": False, "evidence": result["evidence"]}
    state["updatedAt"] = checked_at
    state["lastWorkflowRunId"] = str(workflow_run_id)
    return state, {"schemaVersion": 2, "processed": sum(summary.values()), "states": summary, "remainingPending": sum(1 for source in canonical_sources(registry) if source.get("compatibilityEnrollment", {}).get("state") == "PENDING" and eligible(source, state))}


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
        save(args.output, build_plan(load(args.registry), normalize_state(load(args.state, default={})), args.batch_size))
    elif args.command == "assess":
        roots = {provider: Path(getattr(args, f"{provider}_root")).resolve() for provider in PROVIDERS}
        save(args.output, assess_plan(load(args.plan), roots, load(args.compile_results), args.timeout, max(1, args.fail_threshold)))
    elif args.command == "finalize":
        save(args.output, finalize_results(load(args.profile_results), load(args.parser_results), max(1, args.fail_threshold)))
    elif args.command == "apply":
        registry = load(args.registry)
        state, summary = apply_results(registry, normalize_state(load(args.state, default={})), load(args.results), args.workflow_run_id, args.checked_at)
        save(args.state, state)
        save(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
