#!/usr/bin/env python3
"""Apply fail-closed, evidence-scoped dispositions to an intake report.

This tool deliberately does not mutate the classifier, LKG, approval state, or
promotion state. It can only turn NEEDS_REVIEW into REVIEWED_COMPATIBLE when an
explicit evidence record exactly matches provenance and covers every reported
impact class and path for that source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

HEX40_LEN = 40
PASS = "PASS"
COMPATIBLE = "COMPATIBLE"


def _hex40(value: Any) -> bool:
    return isinstance(value, str) and len(value) == HEX40_LEN and all(c in "0123456789abcdef" for c in value)


def impact_paths(source: dict[str, Any]) -> set[str]:
    own = {item.get("path") for item in source.get("files", []) if isinstance(item, dict)}
    shared = set(source.get("relevantSharedRuntimeFiles", []))
    return {p for p in own | shared if isinstance(p, str) and p}


def load_evidence(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if report.get("schema") != 1:
        return {}
    records = report.get("evidence")
    if not isinstance(records, list):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        canonical = record.get("canonicalId")
        if isinstance(canonical, str) and canonical:
            out.setdefault(canonical, []).append(record)
    return out


def matching_record(
    source: dict[str, Any], base: str, candidate: str, records: list[dict[str, Any]]
) -> dict[str, Any] | None:
    required_classes = set(source.get("changeClasses", []))
    required_paths = impact_paths(source)
    for record in records:
        if record.get("base") != base or record.get("candidate") != candidate:
            continue
        if not _hex40(record.get("base")) or not _hex40(record.get("candidate")):
            continue
        if record.get("result") != PASS or record.get("disposition") != COMPATIBLE:
            continue
        if record.get("infrastructureBlocked") is not False:
            continue
        covered_classes = set(record.get("coveredChangeClasses", []))
        covered_paths = set(record.get("coveredPaths", []))
        if not required_classes.issubset(covered_classes):
            continue
        if not required_paths.issubset(covered_paths):
            continue
        evidence_type = record.get("evidenceType")
        evidence_id = record.get("evidenceId")
        if not isinstance(evidence_type, str) or not evidence_type:
            continue
        if not isinstance(evidence_id, str) or not evidence_id:
            continue
        return record
    return None


def apply_dispositions(intake: dict[str, Any], evidence_report: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(intake))
    base = out.get("base")
    candidate = out.get("candidate")
    if not _hex40(base) or not _hex40(candidate):
        return out
    evidence = load_evidence(evidence_report)
    for source in out.get("sources", []):
        if not isinstance(source, dict) or source.get("automationClass") != "NEEDS_REVIEW":
            continue
        canonical = source.get("canonicalId")
        if not isinstance(canonical, str):
            continue
        record = matching_record(source, base, candidate, evidence.get(canonical, []))
        if record is None:
            continue
        source["state"] = "reviewed-compatible"
        source["action"] = "validate-reviewed-evidence"
        source["automationClass"] = "REVIEWED_COMPATIBLE"
        source["evidenceDisposition"] = {
            "evidenceId": record["evidenceId"],
            "evidenceType": record["evidenceType"],
            "base": base,
            "candidate": candidate,
            "coveredChangeClasses": sorted(set(record.get("coveredChangeClasses", []))),
            "coveredPaths": sorted(set(record.get("coveredPaths", []))),
        }
    affected = [s for s in out.get("sources", []) if isinstance(s, dict) and s.get("state") != "unaffected"]
    blocking = [s for s in affected if s.get("automationClass") == "NEEDS_REVIEW"]
    out["blockingSourceCount"] = len(blocking)
    out["state"] = "hold" if blocking else "clear"
    out["evidenceDispositionSchema"] = 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    intake = json.loads(args.intake.read_text(encoding="utf-8"))
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    result = apply_dispositions(intake, evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.strict and result.get("state") == "hold":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
