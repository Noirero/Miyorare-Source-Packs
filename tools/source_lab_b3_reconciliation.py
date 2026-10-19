#!/usr/bin/env python3
"""Track B Batch 3 reconciliation: classify proven upstream disposition and repair lanes.

This tool is deliberately read-only. It consumes the frozen, post-#157 B3 boundary plus
separately verified upstream evidence and produces deterministic routing. It never mutates
Compatibility Farm authority state, LKG, Retry/Held, canonical IDs, provider preference,
or overlays.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

PHASE = "TRACK_B_BATCH_3_RECONCILIATION"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_DISPOSITIONS = {"UPSTREAM_DEAD", "UPSTREAM_LOCALE_MIGRATION"}
PRIMARY_MISSING = "B3_PRIMARY_IMPLEMENTATION_MISSING"
RUNTIME_UNRESOLVED = "B3_RUNTIME_INCONCLUSIVE_OR_REPAIR_REQUIRED"
PROFILE_BLOCKED_STATES = {"BOTH_PROFILE_BLOCKED", "CANDIDATE_PROFILE_BLOCKED", "LKG_PROFILE_BLOCKED"}
RUNTIME_FAILING_STATES = {"BOTH_RUNTIME_FAILING"}


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def boundary_rows(boundary: dict[str, Any]) -> list[dict[str, Any]]:
    if boundary.get("readOnly") is not True:
        raise ValueError("B3 boundary must be read-only")
    rows = boundary.get("rows")
    if not isinstance(rows, list) or len(rows) != 33:
        raise ValueError(f"B3 boundary must contain exactly 33 rows, got {len(rows) if isinstance(rows, list) else 'invalid'}")
    ids = [row.get("canonicalId") for row in rows if isinstance(row, dict)]
    if len(ids) != 33 or len(set(ids)) != 33 or not all(isinstance(cid, str) and cid for cid in ids):
        raise ValueError("B3 boundary canonical IDs must be 33 unique non-empty strings")
    for row in rows:
        if row.get("nextPhase") != "TRACK_B_BATCH_3":
            raise ValueError(f"unexpected next phase for {row.get('canonicalId')}: {row.get('nextPhase')}")
        if row.get("b3Decision") not in {PRIMARY_MISSING, RUNTIME_UNRESOLVED}:
            raise ValueError(f"unexpected B3 decision for {row.get('canonicalId')}: {row.get('b3Decision')}")
        safety = row.get("safety")
        if not isinstance(safety, dict) or safety.get("readOnly") is not True:
            raise ValueError(f"missing read-only safety proof for {row.get('canonicalId')}")
    return rows


def validate_evidence(boundary: dict[str, Any], evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if evidence.get("schemaVersion") != 1 or evidence.get("phase") != PHASE or evidence.get("readOnly") is not True:
        raise ValueError("invalid B3 reconciliation evidence header")
    cohort = {row["canonicalId"] for row in boundary_rows(boundary)}
    entries = evidence.get("entries")
    if not isinstance(entries, list):
        raise ValueError("evidence entries must be a list")
    mapped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("evidence entry must be an object")
        cid = entry.get("canonicalId")
        if cid not in cohort:
            raise ValueError(f"evidence canonicalId outside B3 cohort: {cid}")
        if cid in mapped:
            raise ValueError(f"duplicate evidence canonicalId: {cid}")
        disposition = entry.get("disposition")
        if disposition not in ALLOWED_DISPOSITIONS:
            raise ValueError(f"unsupported evidence disposition for {cid}: {disposition}")
        commit = entry.get("commit")
        if not isinstance(commit, str) or SHA_RE.fullmatch(commit) is None:
            raise ValueError(f"invalid evidence commit for {cid}: {commit}")
        proof = entry.get("proof")
        if not isinstance(proof, list) or not proof:
            raise ValueError(f"missing evidence proof for {cid}")
        mapped[cid] = entry
    return mapped


def verify_upstream_evidence(evidence: dict[str, Any], evidence_root: Path) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for entry in evidence.get("entries", []):
        cid = entry["canonicalId"]
        commit = entry["commit"]
        checkout = evidence_root / commit
        if not checkout.is_dir():
            raise ValueError(f"missing evidence checkout for {cid}: {checkout}")
        actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        if actual != commit:
            raise ValueError(f"evidence checkout SHA mismatch for {cid}: expected={commit} actual={actual}")
        message = subprocess.check_output(["git", "-C", str(checkout), "show", "-s", "--format=%B", "HEAD"], text=True)
        checks: list[dict[str, Any]] = []
        for proof in entry["proof"]:
            kind = proof.get("type")
            if kind == "commit_message_contains":
                value = proof.get("value")
                if not isinstance(value, str) or value not in message:
                    raise ValueError(f"commit-message proof failed for {cid}: {value!r}")
                checks.append({"type": kind, "value": value, "passed": True})
            elif kind == "file_contains":
                relative = proof.get("path")
                values = proof.get("values")
                if not isinstance(relative, str) or not isinstance(values, list) or not values:
                    raise ValueError(f"invalid file proof for {cid}")
                path = checkout / relative
                if not path.is_file():
                    raise ValueError(f"file proof path missing for {cid}: {relative}")
                text = path.read_text(encoding="utf-8", errors="strict")
                for value in values:
                    if not isinstance(value, str) or value not in text:
                        raise ValueError(f"file proof failed for {cid}: {relative} missing {value!r}")
                checks.append({"type": kind, "path": relative, "values": values, "passed": True})
            else:
                raise ValueError(f"unsupported proof type for {cid}: {kind}")
        verified.append({"canonicalId": cid, "commit": commit, "checks": checks})
    return verified


def _provider_states(row: dict[str, Any]) -> list[dict[str, Any]]:
    providers = row.get("providers")
    if not isinstance(providers, dict):
        return []
    return [value for value in providers.values() if isinstance(value, dict)]


def classify_row(row: dict[str, Any], evidence: dict[str, Any] | None) -> dict[str, Any]:
    cid = row["canonicalId"]
    base = {
        "canonicalId": cid,
        "displayName": row.get("displayName"),
        "b3Decision": row.get("b3Decision"),
        "providers": row.get("providers"),
        "evidence": evidence,
        "safety": {
            "readOnly": True,
            "mutateLastKnownGood": False,
            "mutateRetryHeld": False,
            "mutateCanonicalId": False,
            "promoteProvider": False,
            "approveOverlay": False,
        },
    }
    if row["b3Decision"] == PRIMARY_MISSING:
        if evidence and evidence["disposition"] == "UPSTREAM_DEAD":
            route = "PROVEN_UPSTREAM_DEAD"
            next_action = "NO_PRIMARY_REPAIR_WITHOUT_NEW_REPLACEMENT_EVIDENCE"
        elif evidence and evidence["disposition"] == "UPSTREAM_LOCALE_MIGRATION":
            route = "PROVEN_UPSTREAM_MIGRATION"
            next_action = "B3_TARGETED_REPLACEMENT_IDENTITY_RECONCILIATION"
        else:
            route = "PRIMARY_MISSING_UNRESOLVED"
            next_action = "B3_RESEARCH_REPLACEMENT_OR_TERMINAL_STATUS"
        return {**base, "route": route, "nextAction": next_action}

    states = _provider_states(row)
    names = {state.get("state") for state in states}
    if "CANDIDATE_REGRESSION" in names:
        route = "CANDIDATE_REGRESSION"
        next_action = "B3_BLOCK_CANDIDATE_AND_REPAIR"
    elif names & PROFILE_BLOCKED_STATES:
        route = "NETWORK_OR_PROFILE_BLOCKED"
        next_action = "B3_RECHECK_HOST_NETWORK_OR_ACCESS_PROFILE"
    elif names & RUNTIME_FAILING_STATES:
        comparable = [state for state in states if state.get("state") in RUNTIME_FAILING_STATES]
        if comparable and all(state.get("sameRuntimeFailure") is True for state in comparable):
            route = "SHARED_RUNTIME_FAILURE"
            next_action = "B3_TARGETED_PARSER_REPAIR"
        else:
            route = "RUNTIME_FAILURE_DIVERGED"
            next_action = "B3_DIFFERENTIAL_RUNTIME_INVESTIGATION"
    else:
        route = "RUNTIME_UNRESOLVED"
        next_action = "B3_RUNTIME_INVESTIGATION"
    return {**base, "route": route, "nextAction": next_action}


def build_report(boundary: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    rows = boundary_rows(boundary)
    evidence_map = validate_evidence(boundary, evidence)
    decisions = [classify_row(row, evidence_map.get(row["canonicalId"])) for row in rows]
    routes = Counter(row["route"] for row in decisions)
    actions = Counter(row["nextAction"] for row in decisions)
    if len(decisions) != 33:
        raise ValueError("reconciliation report lost B3 rows")
    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "readOnly": True,
        "source": boundary.get("source"),
        "summary": {
            "rows": len(decisions),
            "routes": dict(sorted(routes.items())),
            "nextActions": dict(sorted(actions.items())),
            "evidenceBackedRows": len(evidence_map),
        },
        "decisions": decisions,
        "safety": {
            "mutatesAuthority": False,
            "mutatesLastKnownGood": False,
            "mutatesRetryHeld": False,
            "mutatesCanonicalIds": False,
            "promotesProvider": False,
            "approvesOverlay": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track B Batch 3 reconciliation",
        "",
        "Read-only routing over the exact post-#157 33-source boundary.",
        "",
        "## Summary",
        "",
    ]
    for name, count in report["summary"]["routes"].items():
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Decisions", "", "| Source | Route | Next action |", "|---|---|---|"])
    for row in report["decisions"]:
        lines.append(f"| `{row['canonicalId'].rsplit(':', 1)[-1]}` | `{row['route']}` | `{row['nextAction']}` |")
    lines.extend([
        "",
        "## Safety",
        "",
        "This report is evidence-only. It does not mutate Compatibility Farm authority, LKG, Retry/Held, canonical IDs, provider preference, or overlay approval.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify-evidence")
    verify.add_argument("--boundary", required=True)
    verify.add_argument("--evidence", required=True)
    verify.add_argument("--evidence-root", required=True)
    verify.add_argument("--output", required=True)

    build = sub.add_parser("build")
    build.add_argument("--boundary", required=True)
    build.add_argument("--evidence", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--markdown-output")

    args = parser.parse_args()
    boundary = load_json(args.boundary)
    evidence = load_json(args.evidence)
    validate_evidence(boundary, evidence)

    if args.command == "verify-evidence":
        result = {
            "schemaVersion": 1,
            "phase": PHASE,
            "readOnly": True,
            "verified": verify_upstream_evidence(evidence, Path(args.evidence_root)),
        }
        save_json(args.output, result)
        return

    report = build_report(boundary, evidence)
    save_json(args.output, report)
    if args.markdown_output:
        target = Path(args.markdown_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
