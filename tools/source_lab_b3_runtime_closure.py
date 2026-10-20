#!/usr/bin/env python3
"""Track B Batch 3 runtime closure over frozen live-access evidence.

This tool layers later live host/access evidence over the immutable post-#157 boundary and
#158 upstream reconciliation. It is read-only: it never mutates Compatibility Farm authority,
LKG, Retry/Held, canonical IDs, provider preference, or parser overlays.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import source_lab_b3_reconciliation as reconciliation

PHASE = "TRACK_B_BATCH_3_RUNTIME_CLOSURE"
LIVE_PHASE = "TRACK_B_BATCH_3_LIVE_RUNTIME_ACCESS"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ALLOWED_DISPOSITIONS = {
    "WAF_BLOCKED",
    "DNS_UNRESOLVED",
    "TLS_UNREACHABLE",
    "DOMAIN_PARKED_OR_REDIRECTED",
}
ACCESS_BLOCKED = {"WAF_BLOCKED", "DNS_UNRESOLVED", "TLS_UNREACHABLE"}


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_live_access_evidence(
    boundary: dict[str, Any], live: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    if live.get("schemaVersion") != 1 or live.get("phase") != LIVE_PHASE or live.get("readOnly") is not True:
        raise ValueError("invalid B3 live-runtime evidence header")

    rows = reconciliation.boundary_rows(boundary)
    runtime_ids = {
        row["canonicalId"]
        for row in rows
        if row.get("b3Decision") == reconciliation.RUNTIME_UNRESOLVED
    }
    if len(runtime_ids) != 9:
        raise ValueError(f"expected exactly 9 runtime-unresolved boundary rows, got {len(runtime_ids)}")

    source = live.get("source")
    if not isinstance(source, dict):
        raise ValueError("live-runtime evidence source metadata missing")
    if not isinstance(source.get("pr"), int) or source["pr"] <= 0:
        raise ValueError("invalid live-runtime source PR")
    if not isinstance(source.get("runId"), int) or source["runId"] <= 0:
        raise ValueError("invalid live-runtime source run")
    if not isinstance(source.get("artifactId"), int) or source["artifactId"] <= 0:
        raise ValueError("invalid live-runtime artifact ID")
    head = source.get("head")
    if not isinstance(head, str) or SHA_RE.fullmatch(head) is None:
        raise ValueError("invalid live-runtime source head")
    workflow_blob = source.get("probeWorkflowBlob")
    if not isinstance(workflow_blob, str) or SHA_RE.fullmatch(workflow_blob) is None:
        raise ValueError("invalid live-runtime probe workflow blob")
    digest = source.get("artifactDigest")
    if not isinstance(digest, str) or DIGEST_RE.fullmatch(digest) is None:
        raise ValueError("invalid live-runtime artifact digest")

    entries = live.get("entries")
    if not isinstance(entries, list):
        raise ValueError("live-runtime evidence entries must be a list")
    mapped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("live-runtime evidence entry must be an object")
        cid = entry.get("canonicalId")
        if cid not in runtime_ids:
            raise ValueError(f"live-runtime evidence outside runtime cohort: {cid}")
        if cid in mapped:
            raise ValueError(f"duplicate live-runtime evidence canonicalId: {cid}")
        disposition = entry.get("disposition")
        if disposition not in ALLOWED_DISPOSITIONS:
            raise ValueError(f"unsupported live-runtime disposition for {cid}: {disposition}")
        observations = entry.get("observations")
        if (
            not isinstance(observations, list)
            or not observations
            or not all(isinstance(value, str) and value.strip() for value in observations)
        ):
            raise ValueError(f"missing live-runtime observations for {cid}")
        mapped[cid] = entry

    if set(mapped) != runtime_ids:
        missing = sorted(runtime_ids - set(mapped))
        extra = sorted(set(mapped) - runtime_ids)
        raise ValueError(f"live-runtime evidence must cover exact nine-source cohort; missing={missing} extra={extra}")
    return mapped


def build_report(
    boundary: dict[str, Any],
    upstream_evidence: dict[str, Any],
    live_access_evidence: dict[str, Any],
) -> dict[str, Any]:
    base = reconciliation.build_report(boundary, upstream_evidence)
    live_map = validate_live_access_evidence(boundary, live_access_evidence)

    decisions: list[dict[str, Any]] = []
    for original in base["decisions"]:
        row = dict(original)
        live = live_map.get(row["canonicalId"])
        if live is not None:
            disposition = live["disposition"]
            if disposition in ACCESS_BLOCKED:
                row["route"] = "LIVE_ACCESS_BLOCKED"
                row["nextAction"] = "B3_RECHECK_HOST_NETWORK_OR_ACCESS_PROFILE"
            elif disposition == "DOMAIN_PARKED_OR_REDIRECTED":
                row["route"] = "LIVE_DOMAIN_DISPOSITION"
                row["nextAction"] = "NO_PARSER_REPAIR_WITHOUT_DOMAIN_RECOVERY_EVIDENCE"
            else:  # guarded by validation above
                raise ValueError(f"unhandled live-runtime disposition: {disposition}")
            row["liveAccessEvidence"] = live
        decisions.append(row)

    routes = Counter(row["route"] for row in decisions)
    actions = Counter(row["nextAction"] for row in decisions)
    if len(decisions) != 33:
        raise ValueError("runtime closure report lost B3 rows")

    parser_routes = {
        row["canonicalId"]: row["route"]
        for row in decisions
        if row["canonicalId"] in live_map
        and row["route"] in {"SHARED_RUNTIME_FAILURE", "RUNTIME_FAILURE_DIVERGED", "CANDIDATE_REGRESSION"}
    }
    if parser_routes:
        raise ValueError(f"live access evidence failed to close parser-repair routing: {parser_routes}")

    upstream_count = int(base["summary"].get("evidenceBackedRows", 0))
    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "readOnly": True,
        "source": {
            "boundary": boundary.get("source"),
            "liveRuntime": live_access_evidence.get("source"),
        },
        "summary": {
            "rows": len(decisions),
            "routes": dict(sorted(routes.items())),
            "nextActions": dict(sorted(actions.items())),
            "upstreamEvidenceBackedRows": upstream_count,
            "liveAccessEvidenceBackedRows": len(live_map),
            "evidenceBackedRows": upstream_count + len(live_map),
        },
        "decisions": decisions,
        "safety": dict(base["safety"]),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track B Batch 3 runtime closure",
        "",
        "Read-only closure over the exact 33-source B3 boundary using upstream disposition and later live host/access evidence.",
        "",
        "## Summary",
        "",
    ]
    for name, count in report["summary"]["routes"].items():
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Decisions", "", "| Source | Route | Next action |", "|---|---|---|"])
    for row in report["decisions"]:
        source = row["canonicalId"].rsplit(":", 1)[-1]
        lines.append(f"| `{source}` | `{row['route']}` | `{row['nextAction']}` |")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This report is evidence-only. It does not mutate Compatibility Farm authority, LKG, Retry/Held, canonical IDs, provider preference, or overlay approval.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary", required=True)
    parser.add_argument("--upstream-evidence", required=True)
    parser.add_argument("--live-access-evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    boundary = load_json(args.boundary)
    upstream = load_json(args.upstream_evidence)
    live = load_json(args.live_access_evidence)
    report = build_report(boundary, upstream, live)
    save_json(args.output, report)
    if args.markdown_output:
        target = Path(args.markdown_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
