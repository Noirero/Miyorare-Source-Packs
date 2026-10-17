#!/usr/bin/env python3
"""Bind real Android/WebView BATCAVE probe evidence to exact runtime-closure provenance.

The binder is deliberately fail-closed. A JVM/build proof remains infrastructure-blocked
unless the Android probe matches the exact candidate and host runtime and proves all of:
- the exact BATCAVE APK was installed and loaded through Miyorare's Mihon runtime;
- a live BATCAVE source request succeeded with a non-empty result;
- Android System WebView was available; and
- the DLE Guard trust cookie was observed after the source request.

A missing/negative runtime signal is evidence of an unresolved requirement, not permission
to weaken the gate.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")
CANONICAL = "miyorare:miyorare-en:BATCAVE"
PROVIDER_HOST = "batcave.biz"


def _hex40(value: Any) -> bool:
    return isinstance(value, str) and HEX40.fullmatch(value) is not None


def _single_runtime_proof(report: dict[str, Any], *, base: str, candidate: str) -> dict[str, Any]:
    if report.get("schema") != 1 or report.get("base") != base or report.get("candidate") != candidate:
        raise ValueError("runtime proof envelope does not match exact base/candidate")
    proofs = report.get("proofs")
    if not isinstance(proofs, list):
        raise ValueError("runtime proof list is missing")
    matches = [
        proof
        for proof in proofs
        if isinstance(proof, dict) and proof.get("canonicalId") == CANONICAL
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one BATCAVE runtime proof, got {len(matches)}")
    proof = matches[0]
    if proof.get("baseRevision") != base:
        raise ValueError("runtime proof base revision mismatch")
    if proof.get("candidateRevision") != candidate or proof.get("runtimeClosureRevision") != candidate:
        raise ValueError("runtime proof candidate revision mismatch")
    if proof.get("requiresAndroidWebView") is not True:
        raise ValueError("BATCAVE runtime proof must require Android WebView")
    return proof


def _probe_matches(
    probe: dict[str, Any], *, candidate: str, miyorare_revision: str
) -> bool:
    return (
        probe.get("schema") == 1
        and probe.get("canonicalId") == CANONICAL
        and probe.get("candidateRevision") == candidate
        and probe.get("miyorareRevision") == miyorare_revision
        and probe.get("providerHost") == PROVIDER_HOST
        and probe.get("runtime") == "miyorare-android-instrumentation"
    )


def android_webview_proven(probe: dict[str, Any]) -> bool:
    webview = probe.get("webView")
    run_id = probe.get("workflowRunId")
    return (
        isinstance(webview, dict)
        and isinstance(run_id, int)
        and run_id > 0
        and probe.get("extensionInstallSucceeded") is True
        and probe.get("extensionLoadSucceeded") is True
        and probe.get("sourceName") == "BatCave"
        and probe.get("sourceRequestSucceeded") is True
        and isinstance(probe.get("sourceResultCount"), int)
        and probe.get("sourceResultCount") > 0
        and probe.get("dleGuardTrustCookieObserved") is True
        and webview.get("available") is True
        and isinstance(webview.get("packageName"), str)
        and bool(webview.get("packageName"))
        and isinstance(webview.get("versionName"), str)
        and bool(webview.get("versionName"))
    )


def bind(
    runtime_report: dict[str, Any],
    probe: dict[str, Any],
    *,
    base: str,
    candidate: str,
    miyorare_revision: str,
) -> dict[str, Any]:
    if not _hex40(base) or not _hex40(candidate) or not _hex40(miyorare_revision):
        raise ValueError("base, candidate, and Miyorare revision must be exact 40-character SHAs")

    runtime_proof = _single_runtime_proof(runtime_report, base=base, candidate=candidate)
    if not _probe_matches(probe, candidate=candidate, miyorare_revision=miyorare_revision):
        raise ValueError("Android probe provenance does not match exact BATCAVE candidate/host")

    out = copy.deepcopy(runtime_report)
    proof = next(item for item in out["proofs"] if item.get("canonicalId") == CANONICAL)
    positive = runtime_proof.get("result") == "PASS" and android_webview_proven(probe)

    webview = probe.get("webView") if isinstance(probe.get("webView"), dict) else {}
    binding = {
        "schemaVersion": 1,
        "runtime": "miyorare-android-instrumentation",
        "miyorareRevision": miyorare_revision,
        "candidateRevision": candidate,
        "workflowRunId": probe.get("workflowRunId"),
        "extensionPackageName": probe.get("extensionPackageName"),
        "sourceRequestSucceeded": probe.get("sourceRequestSucceeded") is True,
        "sourceResultCount": probe.get("sourceResultCount", 0),
        "dleGuardTrustCookieObserved": probe.get("dleGuardTrustCookieObserved") is True,
        "webViewPackageName": webview.get("packageName"),
        "webViewVersion": webview.get("versionName"),
        "probeError": probe.get("error"),
        "androidWebViewExecutionProven": positive,
    }
    proof["androidWebViewEvidence"] = binding
    proof["androidWebViewExecutionProven"] = positive
    proof["infrastructureBlocked"] = not positive

    if positive:
        run_id = probe["workflowRunId"]
        proof["evidenceId"] = f"github-run:{run_id}:{CANONICAL}:android-webview"

    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-proof", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--miyorare-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runtime_report = json.loads(args.runtime_proof.read_text(encoding="utf-8"))
    probe = json.loads(args.probe.read_text(encoding="utf-8"))
    result = bind(
        runtime_report,
        probe,
        base=args.base,
        candidate=args.candidate,
        miyorare_revision=args.miyorare_revision,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
