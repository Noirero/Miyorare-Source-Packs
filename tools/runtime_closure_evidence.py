#!/usr/bin/env python3
"""Derive source-scoped Contract-v1 evidence from executed runtime closure proof.

This helper is intentionally fail-closed.  It never treats an intake path as
covered merely because it was reported by the classifier.  A path is covered
only when execution evidence explicitly proves that exact path participated in
the tested candidate runtime closure.  Android WebView-dependent sources also
require explicit Android WebView execution proof.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")


def impact_paths(source: dict[str, Any]) -> set[str]:
    own = {x.get("path") for x in source.get("files", []) if isinstance(x, dict)}
    shared = set(source.get("relevantSharedRuntimeFiles", []))
    return {p for p in own | shared if isinstance(p, str) and p}


def source_by_id(intake: dict[str, Any], canonical: str) -> dict[str, Any] | None:
    for source in intake.get("sources", []):
        if isinstance(source, dict) and source.get("canonicalId") == canonical:
            return source
    return None


def derive(intake: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
    base = intake.get("base")
    candidate = intake.get("candidate")
    records: list[dict[str, Any]] = []
    if not isinstance(base, str) or not HEX40.fullmatch(base):
        return {"schema": 1, "evidence": records}
    if not isinstance(candidate, str) or not HEX40.fullmatch(candidate):
        return {"schema": 1, "evidence": records}
    if execution.get("schema") != 1 or execution.get("base") != base or execution.get("candidate") != candidate:
        return {"schema": 1, "evidence": records}

    for proof in execution.get("proofs", []):
        if not isinstance(proof, dict):
            continue
        canonical = proof.get("canonicalId")
        source = source_by_id(intake, canonical) if isinstance(canonical, str) else None
        if source is None or source.get("automationClass") != "NEEDS_REVIEW":
            continue
        if proof.get("result") != "PASS" or proof.get("infrastructureBlocked") is not False:
            continue
        if proof.get("candidateRevision") != candidate:
            continue
        if proof.get("runtimeClosureRevision") != candidate:
            continue
        evidence_id = proof.get("evidenceId")
        if not isinstance(evidence_id, str) or not evidence_id:
            continue

        required_paths = impact_paths(source)
        executed_paths = {p for p in proof.get("executedRuntimeClosurePaths", []) if isinstance(p, str) and p}
        if not required_paths.issubset(executed_paths):
            continue
        required_classes = {c for c in source.get("changeClasses", []) if isinstance(c, str)}
        exercised_classes = {c for c in proof.get("exercisedChangeClasses", []) if isinstance(c, str)}
        if not required_classes.issubset(exercised_classes):
            continue
        if proof.get("requiresAndroidWebView") is True and proof.get("androidWebViewExecutionProven") is not True:
            continue

        records.append({
            "canonicalId": canonical,
            "base": base,
            "candidate": candidate,
            "result": "PASS",
            "disposition": "COMPATIBLE",
            "infrastructureBlocked": False,
            "evidenceType": "runtime-closure-execution",
            "evidenceId": evidence_id,
            "coveredChangeClasses": sorted(required_classes),
            "coveredPaths": sorted(required_paths),
        })
    return {"schema": 1, "evidence": records}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    intake = json.loads(args.intake.read_text(encoding="utf-8"))
    execution = json.loads(args.execution.read_text(encoding="utf-8"))
    result = derive(intake, execution)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
