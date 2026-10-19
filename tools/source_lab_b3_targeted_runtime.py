#!/usr/bin/env python3
"""Track B Batch 3: targeted primary discovery and differential runtime planning."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

PRIMARY = ("uma", "gekkoushi")
B3_PHASE = "TRACK_B_BATCH_3"
NORMALIZE_RE = re.compile(r"[^A-Z0-9]+")
URL_RE = re.compile(r"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\d+)?", re.I)
BASE_URL_RE = re.compile(
    r"\b(?:baseUrl|baseURL|BASE_URL)\s*(?:=|:)\s*[\"']https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\d+)?",
    re.I,
)
QUOTED_HOST_RE = re.compile(r"[\"']([A-Za-z0-9](?:[A-Za-z0-9.-]*\.)[A-Za-z]{2,})[\"']")


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize(value: Any) -> str:
    return NORMALIZE_RE.sub("", str(value or "").upper())


def infer_host(text: str) -> str | None:
    for pattern in (BASE_URL_RE, URL_RE):
        match = pattern.search(text)
        if match:
            return match.group(1).lower().rstrip(".")
    quoted = QUOTED_HOST_RE.findall(text)
    return quoted[-1].lower().rstrip(".") if quoted else None


def read_locator(provider: str, root: Path, identity: dict[str, Any]) -> tuple[str | None, str]:
    locator = identity.get("file") if provider in PRIMARY else identity.get("module")
    if not isinstance(locator, str) or not locator:
        return None, ""
    path = root / locator
    if provider in PRIMARY:
        if not path.is_file():
            return locator, ""
        return locator, path.read_text(encoding="utf-8", errors="ignore")
    if not path.is_dir():
        return locator, ""
    parts = [
        child.read_text(encoding="utf-8", errors="ignore")
        for child in sorted(path.rglob("*.kt"))
        if child.is_file()
    ]
    return locator, "\n".join(parts)


def reference_fingerprint(row: dict[str, Any], reference_root: Path) -> dict[str, Any]:
    provider = row.get("providers", {}).get("keiyoushi", {})
    identity = provider.get("farmIdentity") if isinstance(provider, dict) else None
    identity = identity if isinstance(identity, dict) else {}
    locator, text = read_locator("keiyoushi", reference_root, identity)
    aliases = {
        normalize(row.get("displayName")),
        normalize(str(row.get("canonicalId", "")).rsplit(":", 1)[-1]),
        normalize(identity.get("sourceName")),
        normalize(Path(locator).name if locator else ""),
    }
    aliases.discard("")
    return {
        "locator": locator,
        "host": infer_host(text) if text else None,
        "aliases": sorted(aliases),
        "referencePresent": bool(text.strip()),
    }


def parser_files(root: Path) -> list[Path]:
    source_root = root / "src"
    if not source_root.is_dir():
        return []
    return sorted(path for path in source_root.rglob("*.kt") if path.is_file())


def candidate_score(path: Path, text: str, fingerprint: dict[str, Any]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    aliases = set(fingerprint.get("aliases") or [])
    path_norm = normalize(path.stem)
    if path_norm and path_norm in aliases:
        score += 140
        reasons.append("EXACT_FILE_STEM")
    path_blob = normalize(str(path))
    if any(alias and alias in path_blob for alias in aliases):
        score += 50
        reasons.append("PATH_ALIAS")
    text_norm = normalize(text[:10000])
    if any(alias and alias in text_norm for alias in aliases):
        score += 35
        reasons.append("SOURCE_ALIAS")
    expected_host = fingerprint.get("host")
    actual_host = infer_host(text)
    if expected_host and actual_host == expected_host:
        score += 220
        reasons.append("EXACT_REFERENCE_HOST")
    return score, reasons


def discover_primary(root: Path, fingerprint: dict[str, Any]) -> dict[str, Any]:
    ranked: list[dict[str, Any]] = []
    for path in parser_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        score, reasons = candidate_score(path, text, fingerprint)
        if score <= 0:
            continue
        ranked.append({
            "file": str(path.relative_to(root)).replace("\\", "/"),
            "score": score,
            "reasons": reasons,
            "host": infer_host(text),
        })
    ranked.sort(key=lambda item: (-item["score"], item["file"]))
    if not ranked:
        return {"state": "NOT_FOUND", "candidates": []}
    best_score = ranked[0]["score"]
    best = [item for item in ranked if item["score"] == best_score]
    # Discovery is deliberately fail-closed. A weak name-only hit or tied best
    # match is evidence for investigation, not authority to bind a source.
    if best_score < 100:
        return {"state": "WEAK_MATCH", "candidates": ranked[:5]}
    if len(best) != 1:
        return {"state": "AMBIGUOUS", "candidates": ranked[:5]}
    return {"state": "FOUND", "match": best[0], "candidates": ranked[:5]}


def _existing_identity(row: dict[str, Any], provider: str) -> dict[str, Any] | None:
    value = row.get("providers", {}).get(provider, {})
    identity = value.get("farmIdentity") if isinstance(value, dict) else None
    return dict(identity) if isinstance(identity, dict) and identity.get("file") else None


def bind_provider(
    row: dict[str, Any],
    provider: str,
    root: Path,
    fingerprint: dict[str, Any],
) -> dict[str, Any]:
    existing = _existing_identity(row, provider)
    if existing:
        locator = root / str(existing["file"])
        if locator.is_file():
            return {
                "state": "BOUND_EXISTING_IDENTITY",
                "identity": existing,
                "discovery": None,
            }
    discovery = discover_primary(root, fingerprint)
    if discovery.get("state") == "FOUND":
        match = discovery["match"]
        return {
            "state": "BOUND_DISCOVERED_IDENTITY",
            "identity": {
                "file": match["file"],
                "sourceName": str(row.get("canonicalId", "")).rsplit(":", 1)[-1],
            },
            "discovery": discovery,
        }
    return {"state": "UNBOUND", "identity": None, "discovery": discovery}


def b3_rows(b2: dict[str, Any]) -> list[dict[str, Any]]:
    rows = b2.get("decisions")
    if not isinstance(rows, list):
        raise ValueError("B2 decisions must be a list")
    selected = [
        row for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("decision"), dict)
        and row["decision"].get("nextPhase") == B3_PHASE
    ]
    expected = b2.get("summary", {}).get("batch3Rows")
    if not isinstance(expected, int) or expected != len(selected):
        raise ValueError(f"B3 cohort mismatch: expected={expected} actual={len(selected)}")
    return selected


def build_plan(
    b2: dict[str, Any],
    candidate_roots: dict[str, Path],
    lkg_roots: dict[str, Path],
    reference_root: Path,
    *,
    candidate_commits: dict[str, str],
    lkg_commits: dict[str, str],
) -> dict[str, Any]:
    rows = b3_rows(b2)
    items: list[dict[str, Any]] = []
    for row in rows:
        canonical_id = str(row["canonicalId"])
        fingerprint = reference_fingerprint(row, reference_root)
        candidate: dict[str, Any] = {}
        lkg: dict[str, Any] = {}
        for provider in PRIMARY:
            candidate[provider] = bind_provider(row, provider, candidate_roots[provider], fingerprint)
            lkg[provider] = bind_provider(row, provider, lkg_roots[provider], fingerprint)
        items.append({
            "canonicalId": canonical_id,
            "displayName": row.get("displayName"),
            "b2Decision": row["decision"],
            "reference": fingerprint,
            "candidate": candidate,
            "lkg": lkg,
        })
    digest_payload = {
        "candidateCommits": candidate_commits,
        "lkgCommits": lkg_commits,
        "canonicalIds": [item["canonicalId"] for item in items],
    }
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest()
    return {
        "schemaVersion": 1,
        "phase": B3_PHASE,
        "readOnly": True,
        "candidateCommits": candidate_commits,
        "lkgCommits": lkg_commits,
        "cohortSha256": digest,
        "count": len(items),
        "items": items,
    }


def runtime_plan(plan: dict[str, Any], side: str) -> dict[str, Any]:
    if side not in {"candidate", "lkg"}:
        raise ValueError("side must be candidate or lkg")
    items: list[dict[str, Any]] = []
    for item in plan.get("items", []):
        providers: list[str] = []
        identities: dict[str, Any] = {}
        for provider in PRIMARY:
            binding = item.get(side, {}).get(provider, {})
            identity = binding.get("identity") if isinstance(binding, dict) else None
            if isinstance(identity, dict) and identity.get("file"):
                providers.append(provider)
                identities[provider] = identity
        if providers:
            items.append({
                "canonicalId": item["canonicalId"],
                "providers": providers,
                "upstreamIdentities": identities,
                "attempts": 0,
                "previousAttempts": 0,
                "lifetimeAttempts": 0,
                "baselineReset": False,
            })
    return {"schemaVersion": 2, "items": items, "count": len(items), "side": side}


def runtime_map(results: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in results.get("results", []):
        if not isinstance(row, dict):
            continue
        canonical_id = row.get("canonicalId")
        provider = row.get("provider")
        if isinstance(canonical_id, str) and provider in PRIMARY:
            mapped[(canonical_id, str(provider))] = row
    return mapped


def profile_map(results: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(results, dict):
        return mapped
    for row in results.get("results", []):
        if not isinstance(row, dict) or not isinstance(row.get("canonicalId"), str):
            continue
        canonical_id = row["canonicalId"]
        profile = row.get("evidence", {}).get("profile", {})
        memberships = profile.get("memberships") if isinstance(profile, dict) else None
        if not isinstance(memberships, list):
            continue
        for membership in memberships:
            if not isinstance(membership, dict) or membership.get("provider") not in PRIMARY:
                continue
            provider = str(membership["provider"])
            mapped[(canonical_id, provider)] = {
                "state": row.get("state"),
                "failureCategory": row.get("failureCategory"),
                "profileGate": profile.get("gate"),
                "selectedProviders": profile.get("selectedProviders"),
                "membership": membership,
            }
    return mapped


def passed(row: dict[str, Any] | None) -> bool:
    return bool(
        row
        and row.get("status") == "PASS"
        and row.get("parserExecution") is True
        and row.get("detailsTraversal") is True
        and row.get("chapterTraversal") is True
        and row.get("pageExtraction") is True
    )


def profile_blocked(row: dict[str, Any] | None) -> bool:
    return bool(
        row
        and isinstance(row.get("membership"), dict)
        and row["membership"].get("profilePass") is not True
    )


def runtime_failure_signature(row: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if not isinstance(row, dict) or passed(row):
        return None
    return (
        row.get("status"),
        row.get("parserExecution"),
        row.get("failureType"),
        " ".join(str(row.get("failureMessage") or "").split()),
        row.get("detailsTraversal"),
        row.get("chapterTraversal"),
        row.get("pageExtraction"),
    )


def classify_provider(
    candidate_binding: dict[str, Any],
    lkg_binding: dict[str, Any],
    candidate_runtime: dict[str, Any] | None,
    lkg_runtime: dict[str, Any] | None,
    candidate_profile: dict[str, Any] | None = None,
    lkg_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_bound = isinstance(candidate_binding.get("identity"), dict)
    lkg_bound = isinstance(lkg_binding.get("identity"), dict)
    candidate_pass = passed(candidate_runtime)
    lkg_pass = passed(lkg_runtime)
    same_failure = (
        runtime_failure_signature(candidate_runtime) is not None
        and runtime_failure_signature(candidate_runtime) == runtime_failure_signature(lkg_runtime)
    )

    if candidate_pass and lkg_pass:
        state = "BOTH_PASS"
    elif candidate_pass and not lkg_pass:
        state = "CANDIDATE_IMPROVES_OR_RESTORES"
    elif not candidate_pass and lkg_pass:
        state = "CANDIDATE_REGRESSION"
    elif not candidate_bound and not lkg_bound:
        state = "NO_PRIMARY_IMPLEMENTATION"
    elif profile_blocked(candidate_profile) and profile_blocked(lkg_profile):
        state = "BOTH_PROFILE_BLOCKED"
    elif profile_blocked(candidate_profile) and candidate_runtime is None:
        state = "CANDIDATE_PROFILE_BLOCKED"
    elif profile_blocked(lkg_profile) and lkg_runtime is None:
        state = "LKG_PROFILE_BLOCKED"
    elif candidate_runtime is not None and lkg_runtime is not None:
        state = "BOTH_RUNTIME_FAILING"
    elif candidate_bound and candidate_runtime is None:
        state = "CANDIDATE_RUNTIME_EVIDENCE_MISSING"
    elif lkg_bound and lkg_runtime is None:
        state = "LKG_RUNTIME_EVIDENCE_MISSING"
    else:
        state = "BOTH_BLOCKED_OR_FAILING"

    return {
        "state": state,
        "candidateBinding": candidate_binding,
        "lkgBinding": lkg_binding,
        "candidateProfile": candidate_profile,
        "lkgProfile": lkg_profile,
        "candidateRuntime": candidate_runtime,
        "lkgRuntime": lkg_runtime,
        "sameRuntimeFailure": same_failure,
    }


def build_report(
    plan: dict[str, Any],
    candidate_results: dict[str, Any],
    lkg_results: dict[str, Any],
    candidate_profile_results: dict[str, Any] | None = None,
    lkg_profile_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    c_map = runtime_map(candidate_results)
    l_map = runtime_map(lkg_results)
    cp_map = profile_map(candidate_profile_results)
    lp_map = profile_map(lkg_profile_results)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    provider_states: Counter[str] = Counter()

    for item in plan.get("items", []):
        canonical_id = item["canonicalId"]
        providers: dict[str, Any] = {}
        states: list[str] = []
        for provider in PRIMARY:
            detail = classify_provider(
                item["candidate"][provider],
                item["lkg"][provider],
                c_map.get((canonical_id, provider)),
                l_map.get((canonical_id, provider)),
                cp_map.get((canonical_id, provider)),
                lp_map.get((canonical_id, provider)),
            )
            providers[provider] = detail
            states.append(detail["state"])
            provider_states[detail["state"]] += 1

        if any(state in {"BOTH_PASS", "CANDIDATE_IMPROVES_OR_RESTORES"} for state in states):
            decision = "B4_CANDIDATE_RUNTIME_PROVEN"
            next_phase = "TRACK_B_BATCH_4"
        elif "CANDIDATE_REGRESSION" in states:
            decision = "B3_TARGETED_REPAIR_REQUIRED"
            next_phase = B3_PHASE
        elif all(state == "NO_PRIMARY_IMPLEMENTATION" for state in states):
            decision = "B3_PRIMARY_IMPLEMENTATION_MISSING"
            next_phase = B3_PHASE
        else:
            decision = "B3_RUNTIME_INCONCLUSIVE_OR_REPAIR_REQUIRED"
            next_phase = B3_PHASE

        counts[decision] += 1
        rows.append({
            "canonicalId": canonical_id,
            "displayName": item.get("displayName"),
            "decision": decision,
            "nextPhase": next_phase,
            "providers": providers,
            "reference": item.get("reference"),
            "safety": {
                "readOnly": True,
                "mutateLastKnownGood": False,
                "mutateRetryHeld": False,
                "mutateCanonicalId": False,
                "adoptReferenceProvider": False,
                "approveOverlay": False,
            },
        })

    return {
        "schemaVersion": 2,
        "phase": B3_PHASE,
        "status": "COMPLETE_WITH_RUNTIME_EVIDENCE",
        "readOnly": True,
        "cohortSha256": plan.get("cohortSha256"),
        "candidateCommits": plan.get("candidateCommits"),
        "lkgCommits": plan.get("lkgCommits"),
        "summary": {
            "rows": len(rows),
            "decisions": dict(counts),
            "providerStates": dict(provider_states),
        },
        "decisions": rows,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track B Batch 3 — Targeted Primary Runtime",
        "",
        f"Status: **{report['status']}**",
        "",
        "This report is read-only. It does not mutate LKG, Retry/Held state, canonical IDs, provider preference, or overlay authority.",
        "",
        f"Rows: **{report['summary']['rows']}**",
        "",
        "## Decisions",
    ]
    for key, value in sorted(report["summary"]["decisions"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Provider evidence states"])
    for key, value in sorted(report["summary"].get("providerStates", {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Sources", ""])
    for row in report["decisions"]:
        active = [
            f"{provider}={detail['state']}"
            for provider, detail in row["providers"].items()
            if detail["state"] != "NO_PRIMARY_IMPLEMENTATION"
        ]
        suffix = f" ({', '.join(active)})" if active else ""
        lines.append(f"- `{row['canonicalId']}` — **{row['decision']}** → `{row['nextPhase']}`{suffix}")
    return "\n".join(lines) + "\n"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--b2-report", required=True)
    plan.add_argument("--uma-candidate-root", required=True)
    plan.add_argument("--gekkoushi-candidate-root", required=True)
    plan.add_argument("--uma-lkg-root", required=True)
    plan.add_argument("--gekkoushi-lkg-root", required=True)
    plan.add_argument("--keiyoushi-reference-root", required=True)
    plan.add_argument("--uma-candidate-commit", required=True)
    plan.add_argument("--gekkoushi-candidate-commit", required=True)
    plan.add_argument("--uma-lkg-commit", required=True)
    plan.add_argument("--gekkoushi-lkg-commit", required=True)
    plan.add_argument("--output", required=True)
    plan.add_argument("--candidate-runtime-plan", required=True)
    plan.add_argument("--lkg-runtime-plan", required=True)

    report = sub.add_parser("report")
    report.add_argument("--plan", required=True)
    report.add_argument("--candidate-results", required=True)
    report.add_argument("--lkg-results", required=True)
    report.add_argument("--candidate-profile-results")
    report.add_argument("--lkg-profile-results")
    report.add_argument("--output", required=True)
    report.add_argument("--markdown-output", required=True)
    return p


def inferred_profile_path(runtime_path: str | Path) -> Path:
    path = Path(runtime_path)
    marker = "-live-results.json"
    if not path.name.endswith(marker):
        return path.with_name(path.stem + "-profile-results.json")
    return path.with_name(path.name[:-len(marker)] + "-profile-results.json")


def optional_profile(explicit: str | None, runtime_path: str) -> dict[str, Any]:
    path = Path(explicit) if explicit else inferred_profile_path(runtime_path)
    return load_json(path) if path.is_file() else {"schemaVersion": 2, "results": []}


def main() -> None:
    args = parser().parse_args()
    if args.command == "plan":
        b2 = load_json(args.b2_report)
        result = build_plan(
            b2,
            {"uma": Path(args.uma_candidate_root), "gekkoushi": Path(args.gekkoushi_candidate_root)},
            {"uma": Path(args.uma_lkg_root), "gekkoushi": Path(args.gekkoushi_lkg_root)},
            Path(args.keiyoushi_reference_root),
            candidate_commits={"uma": args.uma_candidate_commit, "gekkoushi": args.gekkoushi_candidate_commit},
            lkg_commits={"uma": args.uma_lkg_commit, "gekkoushi": args.gekkoushi_lkg_commit},
        )
        save_json(args.output, result)
        save_json(args.candidate_runtime_plan, runtime_plan(result, "candidate"))
        save_json(args.lkg_runtime_plan, runtime_plan(result, "lkg"))
    else:
        result = build_report(
            load_json(args.plan),
            load_json(args.candidate_results),
            load_json(args.lkg_results),
            optional_profile(args.candidate_profile_results, args.candidate_results),
            optional_profile(args.lkg_profile_results, args.lkg_results),
        )
        save_json(args.output, result)
        Path(args.markdown_output).write_text(markdown(result), encoding="utf-8")


if __name__ == "__main__":
    main()
