#!/usr/bin/env python3
"""Track C Batch 5: close ID investigation by routing final remediation evidence to lifecycle.

This layer is read-only. It binds the exact post-#167 remediation artifact to the current
Compatibility Farm state and converts each remaining investigation result into an explicit
lifecycle disposition. `trackCClosed` means Source Lab investigation/decision work is closed;
it does not mean every source is runtime-healthy or publishable.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

PHASE = "TRACK_C_BATCH_5_ID_CLOSURE_HANDOFF"
REMEDIATION_PHASE = "TRACK_C_C3_ID_REMEDIATION_REVALIDATION"
LUMOS = "miyorare:inventory-id:LUMOSKOMIK"
MANGABALL = "miyorare:inventory-id:MANGABALLINDONESIAN"
SOFTKOMIK = "miyorare:inventory-id:SOFTKOMIK"
EXPECTED_IDS = (LUMOS, MANGABALL, SOFTKOMIK)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

PENDING_WORKER = ".github/workflows/source-lab-pending-worker.yml"
HELD_OBSERVABILITY = "tools/source_held_observability.py"


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rows_by_id(rows: Any, *, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError(f"{label} must be a list")
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = row.get("canonicalId")
        if not isinstance(cid, str):
            continue
        if cid in mapped:
            raise ValueError(f"duplicate {label} row: {cid}")
        mapped[cid] = row
    return mapped


def validate_artifact_metadata(meta: dict[str, Any]) -> None:
    for key in ("runId", "artifactId"):
        if not isinstance(meta.get(key), int) or meta[key] <= 0:
            raise ValueError(f"invalid remediation artifact {key}")
    for key in ("headSha", "digest"):
        value = meta.get(key)
        pattern = SHA_RE if key == "headSha" else DIGEST_RE
        if not isinstance(value, str) or pattern.fullmatch(value) is None:
            raise ValueError(f"invalid remediation artifact {key}")


def validate_remediation(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if (
        report.get("schemaVersion") != 1
        or report.get("phase") != REMEDIATION_PHASE
        or report.get("language") != "id"
        or report.get("readOnly") is not True
    ):
        raise ValueError("invalid #167 remediation report")
    decisions = rows_by_id(report.get("decisions"), label="remediation decisions")
    if tuple(decisions) != EXPECTED_IDS:
        raise ValueError(f"unexpected remediation IDs: {tuple(decisions)}")
    expected = {
        LUMOS: "LUMOS_PROVIDER_DIVERGENCE_CONFIRMED",
        MANGABALL: "MANGABALL_UPSTREAM_RUNTIME_FAILURE_CONFIRMED",
        SOFTKOMIK: "SOFTKOMIK_RUNTIME_FAILURE_AFTER_PUBLIC_AUTH_OVERRIDE",
    }
    for cid, decision in expected.items():
        if decisions[cid].get("decision") != decision:
            raise ValueError(f"unexpected #167 decision for {cid}")
        safety = decisions[cid].get("safety")
        if not (
            isinstance(safety, dict)
            and safety.get("readOnly") is True
            and safety.get("authorityMutation") is False
            and safety.get("providerAdoption") is False
            and safety.get("credentialInjection") is False
        ):
            raise ValueError(f"invalid remediation safety for {cid}")
    return decisions


def registry_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if registry.get("schemaVersion") != 1:
        raise ValueError("unsupported Compatibility Farm registry")
    return rows_by_id(registry.get("sources"), label="Farm registry")


def worker_by_id(worker: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if worker.get("schemaVersion") != 2 or not isinstance(worker.get("sources"), dict):
        raise ValueError("unsupported pending worker state")
    return {
        cid: row
        for cid, row in worker["sources"].items()
        if isinstance(cid, str) and isinstance(row, dict)
    }


def runtime_row(decision: dict[str, Any], provider: str) -> dict[str, Any]:
    runtime = decision.get("runtime")
    row = runtime.get(provider) if isinstance(runtime, dict) else None
    if not isinstance(row, dict):
        raise ValueError(f"missing remediation runtime evidence for {decision.get('canonicalId')}:{provider}")
    return row


def runtime_pass(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "PASS"
        and row.get("parserExecution") is True
        and row.get("detailsTraversal") is True
        and row.get("chapterTraversal") is True
        and row.get("pageExtraction") is True
    )


def provider_identity(source: dict[str, Any], provider: str) -> dict[str, Any]:
    identities = source.get("upstreamIdentities")
    value = identities.get(provider) if isinstance(identities, dict) else None
    return value if isinstance(value, dict) else {}


def classify_lumos(remediation: dict[str, Any], source: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any]:
    g = runtime_row(remediation, "gekkoushi")
    u = runtime_row(remediation, "uma")
    if runtime_pass(g) or not runtime_pass(u):
        raise ValueError("Lumos closure requires #167 Gekkoushi FAIL + UMA full PASS")

    providers = sorted(str(value) for value in source.get("providers", []) if isinstance(value, str))
    uma_identity = provider_identity(source, "uma")
    worker_selected = sorted(str(value) for value in worker.get("selectedProviders", []) if isinstance(value, str))
    already_reconciled = (
        providers == ["uma"]
        and uma_identity.get("sourceName") == "LUMOSKOMIK"
        and uma_identity.get("file") == "src/main/kotlin/tsuki/site/id/LumosKomik.kt"
        and source.get("updateState") == "PROMOTED"
        and worker.get("state") == "APPROVED"
        and worker.get("approvalState") == "APPROVED"
        and worker_selected == ["uma"]
    )
    return {
        "canonicalId": LUMOS,
        "closureResolved": True,
        "disposition": "LUMOS_RECONCILIATION_ALREADY_SATISFIED_BY_LIFECYCLE" if already_reconciled else "LUMOS_PROVIDER_RECONCILIATION_LIFECYCLE_HANDOFF",
        "lifecycleCategory": "PROVIDER_RECONCILIATION",
        "operationalHandoffRequired": not already_reconciled,
        "nextAction": "NO_ACTION_AUTHORITY_ALREADY_UMA_ONLY" if already_reconciled else "EXISTING_SOURCE_LAB_LIFECYCLE_RECONCILIATION",
        "authoritySnapshot": {
            "providers": providers,
            "updateState": source.get("updateState"),
            "umaIdentity": uma_identity,
            "workerState": worker.get("state"),
            "workerApprovalState": worker.get("approvalState"),
            "workerSelectedProviders": worker_selected,
        },
        "evidence": {"gekkoushiRuntimePass": False, "umaRuntimePass": True},
    }


def classify_mangaball(remediation: dict[str, Any], source: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any]:
    row = runtime_row(remediation, "uma")
    if row.get("parserExecution") is not True or row.get("status") != "FAIL":
        raise ValueError("MangaBall closure requires a real executed parser failure")
    if "HttpStatusException" not in str(row.get("failureMessage") or ""):
        raise ValueError("MangaBall closure requires the corrected #167 HTTP runtime failure")

    old_parser = worker.get("evidence", {}).get("parser", {}) if isinstance(worker.get("evidence"), dict) else {}
    old_members = old_parser.get("memberships", []) if isinstance(old_parser, dict) else []
    old_messages = " ".join(str(item.get("failureMessage") or "") for item in old_members if isinstance(item, dict))
    stale_harness_evidence = "NoSuchMethodException" in old_messages

    return {
        "canonicalId": MANGABALL,
        "closureResolved": True,
        "disposition": "MANGABALL_SOURCE_PARSER_FAILURE_ROUTED_TO_RETRY",
        "lifecycleCategory": "SOURCE_PARSER_FAILURE",
        "operationalHandoffRequired": True,
        "nextAction": PENDING_WORKER,
        "retrySemantics": {"terminal": False, "genericFailThresholdAutoHold": False, "ownerActionRequired": False},
        "authoritySnapshot": {
            "providers": sorted(str(v) for v in source.get("providers", []) if isinstance(v, str)),
            "approvalState": source.get("approvalState"),
            "updateState": source.get("updateState"),
            "workerState": worker.get("state"),
            "workerFailureCategory": worker.get("failureCategory"),
            "workerEvidencePredatesCorrectedHarness": stale_harness_evidence,
        },
        "evidence": {"parserExecution": True, "runtimePass": False, "failureType": row.get("failureType"), "failureMessage": row.get("failureMessage")},
    }


def classify_softkomik(remediation: dict[str, Any], source: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any]:
    row = runtime_row(remediation, "uma")
    message = str(row.get("failureMessage") or "")
    if row.get("parserExecution") is not True or row.get("status") != "FAIL":
        raise ValueError("SoftKomik closure requires a real executed parser failure")
    if "login" not in message.lower():
        raise ValueError("SoftKomik closure requires explicit login-required runtime evidence")

    auth_type = worker.get("authType")
    if auth_type not in {"TOKEN", "FORM", "COOKIE"}:
        raise ValueError("SoftKomik live worker state no longer records an auth requirement")

    return {
        "canonicalId": SOFTKOMIK,
        "closureResolved": True,
        "disposition": "SOFTKOMIK_AUTH_REQUIRED_ROUTED_TO_OWNER_ACTION",
        "lifecycleCategory": "AUTH_REQUIRED",
        "operationalHandoffRequired": True,
        "nextAction": "OWNER_AUTH_ACCESS_OR_LEAVE_HELD",
        "lifecycleMechanisms": [PENDING_WORKER, HELD_OBSERVABILITY],
        "authSemantics": {"authType": auth_type, "credentialInjectionAllowed": False, "autoCredentialProvisioning": False, "holdCandidate": True},
        "authoritySnapshot": {
            "providers": sorted(str(v) for v in source.get("providers", []) if isinstance(v, str)),
            "approvalState": source.get("approvalState"),
            "updateState": source.get("updateState"),
            "workerState": worker.get("state"),
            "workerApprovalState": worker.get("approvalState"),
            "workerAuthType": auth_type,
        },
        "evidence": {"parserExecution": True, "runtimePass": False, "failureType": row.get("failureType"), "failureMessage": message},
    }


def build_report(remediation: dict[str, Any], registry: dict[str, Any], worker: dict[str, Any], artifact_meta: dict[str, Any], current_refs: dict[str, str]) -> dict[str, Any]:
    validate_artifact_metadata(artifact_meta)
    decisions = validate_remediation(remediation)
    farm = registry_by_id(registry)
    workers = worker_by_id(worker)
    for cid in EXPECTED_IDS:
        if cid not in farm:
            raise ValueError(f"Farm authority missing {cid}")
        if cid not in workers:
            raise ValueError(f"pending worker state missing {cid}")

    rows = [
        classify_lumos(decisions[LUMOS], farm[LUMOS], workers[LUMOS]),
        classify_mangaball(decisions[MANGABALL], farm[MANGABALL], workers[MANGABALL]),
        classify_softkomik(decisions[SOFTKOMIK], farm[SOFTKOMIK], workers[SOFTKOMIK]),
    ]
    unresolved = [row["canonicalId"] for row in rows if row["closureResolved"] is not True]
    handoffs = [row["canonicalId"] for row in rows if row["operationalHandoffRequired"] is True]
    counts = Counter(str(row["disposition"]) for row in rows)
    track_closed = not unresolved

    for key in ("sourcePacksAfterRemediation", "compatibilityFarm"):
        value = current_refs.get(key)
        if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
            raise ValueError(f"invalid current ref: {key}")

    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "language": "id",
        "readOnly": True,
        "trackCClosed": track_closed,
        "status": "TRACK_C_CLOSED_WITH_OPERATIONAL_HANDOFFS" if track_closed and handoffs else "TRACK_C_CLOSED_BASELINE_CLEAN" if track_closed else "TRACK_C_CLOSURE_INCOMPLETE",
        "closureSemantics": {
            "meaning": "Source Lab investigation and decision work is complete",
            "doesNotMeanAllSourcesRuntimeHealthy": True,
            "doesNotAuthorizePublishing": True,
            "doesNotAuthorizeProviderMutation": True,
        },
        "source": {"remediationArtifact": dict(artifact_meta), "currentRefs": dict(current_refs)},
        "summary": {
            "sources": len(rows),
            "closureResolved": len(rows) - len(unresolved),
            "unresolved": len(unresolved),
            "unresolvedCanonicalIds": unresolved,
            "operationalHandoffs": len(handoffs),
            "operationalHandoffCanonicalIds": handoffs,
            "dispositions": dict(sorted(counts.items())),
        },
        "decisions": rows,
        "safetyBoundary": {
            "mutateFarmAuthority": False,
            "mutateLastKnownGood": False,
            "mutateRetryHeld": False,
            "mutateCanonicalId": False,
            "mutateConsumerPackaging": False,
            "autoAdoptProvider": False,
            "injectCredentials": False,
            "publishSource": False,
        },
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track C Batch 5 — ID Closure & Lifecycle Handoff",
        "",
        f"- Status: `{report['status']}`",
        f"- Track C closed: `{str(report['trackCClosed']).lower()}`",
        f"- Evidence-backed rows: `{report['summary']['closureResolved']}/{report['summary']['sources']}`",
        f"- Operational handoffs: `{report['summary']['operationalHandoffs']}`",
        "",
        "Track closure means the Source Lab investigation/decision track is complete. It does **not** mean every source is runtime-healthy or publishable.",
        "",
        "| Source | Disposition | Next action |",
        "|---|---|---|",
    ]
    for row in report["decisions"]:
        source = row["canonicalId"].rsplit(":", 1)[-1]
        lines.append(f"| `{source}` | `{row['disposition']}` | `{row['nextAction']}` |")
    lines.extend(["", "## Safety", "", "Read-only closure. No provider selection, Farm authority, LKG, Retry/Held, canonical ID, consumer packaging, credential, or publish state is mutated.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remediation-report", required=True)
    parser.add_argument("--farm-registry", required=True)
    parser.add_argument("--worker-state", required=True)
    parser.add_argument("--artifact-meta", required=True)
    parser.add_argument("--source-packs-commit", required=True)
    parser.add_argument("--farm-commit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    args = parser.parse_args()
    report = build_report(load(args.remediation_report), load(args.farm_registry), load(args.worker_state), load(args.artifact_meta), {"sourcePacksAfterRemediation": args.source_packs_commit, "compatibilityFarm": args.farm_commit})
    save(args.output, report)
    if args.markdown_output:
        Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
