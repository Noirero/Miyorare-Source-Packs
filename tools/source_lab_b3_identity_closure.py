#!/usr/bin/env python3
"""Close the remaining Track B Batch 3 identity-only rows without authority mutation.

This layer consumes the immutable Batch 3 boundary, upstream-disposition evidence, live-runtime
closure evidence, and frozen Compatibility Farm / Keiyoushi identity evidence. It only produces
a read-only report. It never mutates registry authority, LKG, Retry/Held, canonical IDs, provider
preference, health, or parser overlays.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path
from typing import Any

import source_lab_b3_runtime_closure as runtime_closure

PHASE = "TRACK_B_BATCH_3_IDENTITY_CLOSURE"
EVIDENCE_PHASE = "TRACK_B_BATCH_3_IDENTITY_CLOSURE_EVIDENCE"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DEAD = "UPSTREAM_DEAD_REMOVAL"
MIGRATION = "LOCALE_MIGRATION_CONFIRMED"
CMANHUA = "miyorare:inventory-en:CMANHUA"


def _require_sha(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise ValueError(f"invalid identity-closure source SHA: {key}")
    return value


def validate_identity_evidence(
    runtime_report: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    if (
        evidence.get("schemaVersion") != 1
        or evidence.get("phase") != EVIDENCE_PHASE
        or evidence.get("readOnly") is not True
    ):
        raise ValueError("invalid B3 identity-closure evidence header")

    source = evidence.get("source")
    if not isinstance(source, dict):
        raise ValueError("identity-closure source metadata missing")
    for key in (
        "farmRegistryCommit",
        "farmRegistryBlob",
        "keiyoushiCurrentHead",
        "removeDownCommit",
        "removeDownParent",
        "removeDeadCommit",
        "removeDeadParent",
        "cmanhuaMigrationCommit",
        "cmanhuaMigrationParent",
    ):
        _require_sha(source, key)

    decisions = {row["canonicalId"]: row for row in runtime_report.get("decisions", [])}
    unresolved = {
        cid for cid, row in decisions.items() if row.get("route") == "PRIMARY_MISSING_UNRESOLVED"
    }
    if len(unresolved) != 8:
        raise ValueError(f"expected exactly 8 primary-missing rows, got {len(unresolved)}")
    if decisions.get(CMANHUA, {}).get("route") != "PROVEN_UPSTREAM_MIGRATION":
        raise ValueError("CManhua must already be proven as an upstream migration")
    expected = unresolved | {CMANHUA}

    entries = evidence.get("entries")
    if not isinstance(entries, list):
        raise ValueError("identity-closure entries must be a list")

    mapped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("identity-closure entry must be an object")
        cid = entry.get("canonicalId")
        if cid not in expected:
            raise ValueError(f"identity evidence outside expected cohort: {cid}")
        if cid in mapped:
            raise ValueError(f"duplicate identity evidence canonicalId: {cid}")

        disposition = entry.get("disposition")
        required_disposition = MIGRATION if cid == CMANHUA else DEAD
        if disposition != required_disposition:
            raise ValueError(f"unexpected disposition for {cid}: {disposition}")

        farm = entry.get("farmIdentity")
        if not isinstance(farm, dict) or farm.get("provider") != "keiyoushi":
            raise ValueError(f"invalid Farm provider identity for {cid}")
        if not isinstance(farm.get("module"), str) or not farm["module"].startswith("src/en/"):
            raise ValueError(f"invalid Farm module for {cid}")
        if not isinstance(farm.get("sourceId"), int) or farm["sourceId"] <= 0:
            raise ValueError(f"invalid Farm source ID for {cid}")
        if not isinstance(farm.get("sourceName"), str) or not farm["sourceName"].strip():
            raise ValueError(f"invalid Farm source name for {cid}")
        if "baseUrl" in farm and (
            not isinstance(farm["baseUrl"], str) or not farm["baseUrl"].startswith("https://")
        ):
            raise ValueError(f"invalid Farm base URL for {cid}")

        proof = entry.get("proof")
        if not isinstance(proof, dict):
            raise ValueError(f"missing proof for {cid}")
        for key in ("commit", "parent"):
            value = proof.get(key)
            if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
                raise ValueError(f"invalid proof {key} for {cid}")
        marker = proof.get("commitMessageMarker")
        if not isinstance(marker, str) or not marker.strip():
            raise ValueError(f"missing commit marker for {cid}")

        if cid == CMANHUA:
            if proof.get("targetModule") != "src/zh/cmanhua":
                raise ValueError("CManhua migration target module must be src/zh/cmanhua")
            if proof.get("targetLanguage") != "zh":
                raise ValueError("CManhua migration target language must be zh")
            if proof.get("targetPackageName") != "en.cmanhua":
                raise ValueError("CManhua compatibility package must remain en.cmanhua")
            if proof.get("targetBaseUrl") != "https://cmanhua.com":
                raise ValueError("unexpected CManhua migration target URL")

        mapped[cid] = entry

    if set(mapped) != expected:
        missing = sorted(expected - set(mapped))
        extra = sorted(set(mapped) - expected)
        raise ValueError(f"identity evidence must cover exact cohort; missing={missing} extra={extra}")
    return mapped


def build_report(
    boundary: dict[str, Any],
    upstream_evidence: dict[str, Any],
    live_access_evidence: dict[str, Any],
    identity_evidence: dict[str, Any],
) -> dict[str, Any]:
    base = runtime_closure.build_report(boundary, upstream_evidence, live_access_evidence)
    identity_map = validate_identity_evidence(base, identity_evidence)

    decisions: list[dict[str, Any]] = []
    newly_closed = 0
    for original in base["decisions"]:
        row = dict(original)
        evidence = identity_map.get(row["canonicalId"])
        if evidence is not None:
            if evidence["disposition"] == DEAD:
                if row["route"] != "PRIMARY_MISSING_UNRESOLVED":
                    raise ValueError(f"dead-removal evidence cannot override route {row['route']}")
                row["route"] = "PROVEN_UPSTREAM_DEAD"
                row["nextAction"] = "NO_PRIMARY_REPAIR_WITHOUT_NEW_REPLACEMENT_EVIDENCE"
                newly_closed += 1
            elif evidence["disposition"] == MIGRATION:
                if row["route"] != "PROVEN_UPSTREAM_MIGRATION":
                    raise ValueError("CManhua migration evidence cannot override a non-migration route")
                row["nextAction"] = "NO_EN_PRIMARY_REPAIR_PRESERVE_REFERENCE_ONLY_MIGRATION"
            else:  # guarded by validation
                raise ValueError(f"unhandled identity disposition: {evidence['disposition']}")
            row["identityClosureEvidence"] = evidence
        decisions.append(row)

    if len(decisions) != 33:
        raise ValueError("identity closure report lost Batch 3 rows")
    routes = Counter(row["route"] for row in decisions)
    actions = Counter(row["nextAction"] for row in decisions)
    if routes.get("PRIMARY_MISSING_UNRESOLVED", 0) != 0:
        raise ValueError("identity closure left primary-missing rows unresolved")
    if newly_closed != 8:
        raise ValueError(f"expected 8 newly closed primary-missing rows, got {newly_closed}")

    base_evidence = int(base["summary"].get("evidenceBackedRows", 0))
    unique_evidence = base_evidence + newly_closed
    if unique_evidence != 33:
        raise ValueError(f"expected all 33 Batch 3 rows to be evidence-backed, got {unique_evidence}")

    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "readOnly": True,
        "source": {
            "runtimeClosure": base.get("source"),
            "identityClosure": identity_evidence.get("source"),
        },
        "summary": {
            "rows": len(decisions),
            "routes": dict(sorted(routes.items())),
            "nextActions": dict(sorted(actions.items())),
            "runtimeClosureEvidenceBackedRows": base_evidence,
            "identityEvidenceRows": len(identity_map),
            "newlyClosedPrimaryMissingRows": newly_closed,
            "evidenceBackedRows": unique_evidence,
        },
        "decisions": decisions,
        "safety": dict(base["safety"]),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track B Batch 3 identity closure",
        "",
        "Read-only final reconciliation of the eight former primary-missing Farm identities plus the CManhua locale migration.",
        "",
        "## Summary",
        "",
    ]
    for name, count in report["summary"]["routes"].items():
        lines.append(f"- `{name}`: {count}")
    lines.extend(
        [
            f"- evidence-backed rows: {report['summary']['evidenceBackedRows']}/33",
            "",
            "## Decisions",
            "",
            "| Source | Route | Next action |",
            "|---|---|---|",
        ]
    )
    for row in report["decisions"]:
        source = row["canonicalId"].rsplit(":", 1)[-1]
        lines.append(f"| `{source}` | `{row['route']}` | `{row['nextAction']}` |")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "Evidence-only closure. No Compatibility Farm authority, LKG, Retry/Held, canonical ID, provider preference, health, or parser overlay is mutated.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary", required=True)
    parser.add_argument("--upstream-evidence", required=True)
    parser.add_argument("--live-access-evidence", required=True)
    parser.add_argument("--identity-evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    report = build_report(
        runtime_closure.load_json(args.boundary),
        runtime_closure.load_json(args.upstream_evidence),
        runtime_closure.load_json(args.live_access_evidence),
        runtime_closure.load_json(args.identity_evidence),
    )
    runtime_closure.save_json(args.output, report)
    if args.markdown_output:
        target = Path(args.markdown_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
