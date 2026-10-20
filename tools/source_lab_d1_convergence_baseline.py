#!/usr/bin/env python3
"""Track D D1: converge closed EN/ID audit tracks onto the permanent Source Lab operating model.

D1 is deliberately read-only. It proves that the final Track B and Track C decisions still
match live lifecycle authority, that Last-Known-Good safety remains intact, and that the
permanent automation handoff paths exist. It does not promote providers, alter Farm state,
change Retry/Held, approve sources, mutate consumer packaging, or publish anything.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PHASE = "TRACK_D_D1_CONVERGENCE_BASELINE"
NEXT_STAGE = "TRACK_D_D2_PROVIDER_PREFERENCE_RECOVERY"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

LUMOS = "miyorare:inventory-id:LUMOSKOMIK"
MANGABALL = "miyorare:inventory-id:MANGABALLINDONESIAN"
SOFTKOMIK = "miyorare:inventory-id:SOFTKOMIK"
EXPECTED_IDS = (LUMOS, MANGABALL, SOFTKOMIK)


class ConvergenceError(ValueError):
    pass


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConvergenceError(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise ConvergenceError(f"invalid {label} SHA")
    return value


def rows_by_id(rows: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        raise ConvergenceError(f"{label} must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("canonicalId"), str):
            continue
        cid = row["canonicalId"]
        if cid in result:
            raise ConvergenceError(f"duplicate {label} row: {cid}")
        result[cid] = row
    return result


def validate_baseline(baseline: dict[str, Any]) -> None:
    if baseline.get("schemaVersion") != 1 or baseline.get("phase") != PHASE or baseline.get("readOnly") is not True:
        raise ConvergenceError("invalid D1 baseline header")
    require_sha(baseline.get("sourcePacksAfterTrackC"), "post-Track-C Source-Packs")
    planning = baseline.get("planningRefs")
    if not isinstance(planning, dict):
        raise ConvergenceError("planningRefs missing")
    for key in ("sourceInventory", "compatibilityFarm", "miyorareAmain2"):
        require_sha(planning.get(key), f"planning {key}")

    track_b = baseline.get("trackB")
    if not isinstance(track_b, dict) or track_b.get("phase") != "TRACK_B_BATCH_4_ADOPTION_DRIFT":
        raise ConvergenceError("invalid Track B closure binding")
    if track_b.get("requiredStatus") != "TRACK_B_CLOSED_BASELINE_CLEAN":
        raise ConvergenceError("D1 requires clean Track B closure")

    track_c = baseline.get("trackC")
    if not isinstance(track_c, dict) or track_c.get("phase") != "TRACK_C_BATCH_5_ID_CLOSURE_HANDOFF":
        raise ConvergenceError("invalid Track C closure binding")
    if track_c.get("requiredStatus") != "TRACK_C_CLOSED_WITH_OPERATIONAL_HANDOFFS":
        raise ConvergenceError("unexpected Track C closure status binding")
    if track_c.get("monitorPhase") != "TRACK_C_BATCH_4_ID_ADOPTION_DRIFT" or track_c.get("requiredMonitorStatus") != "TRACK_C_C4_COMPLETE_WITH_C3_REMEDIATION":
        raise ConvergenceError("invalid Track C drift-monitor binding")
    artifact = track_c.get("artifact")
    if not isinstance(artifact, dict):
        raise ConvergenceError("Track C artifact binding missing")
    if not isinstance(artifact.get("runId"), int) or not isinstance(artifact.get("artifactId"), int):
        raise ConvergenceError("Track C artifact ids invalid")
    require_sha(artifact.get("headSha"), "Track C artifact head")
    if not isinstance(artifact.get("digest"), str) or not artifact["digest"].startswith("sha256:"):
        raise ConvergenceError("Track C artifact digest invalid")

    dispositions = baseline.get("expectedTrackCDispositions")
    if not isinstance(dispositions, dict) or set(dispositions) != set(EXPECTED_IDS):
        raise ConvergenceError("unexpected Track C disposition cohort")

    automation = baseline.get("permanentAutomation")
    if not isinstance(automation, dict) or not automation:
        raise ConvergenceError("permanent automation map missing")
    if baseline.get("nextStage") != NEXT_STAGE:
        raise ConvergenceError("D1 next stage must be D2 provider preference/recovery")


def validate_track_b(report: dict[str, Any], baseline: dict[str, Any]) -> None:
    if report.get("schemaVersion") != 1 or report.get("phase") != baseline["trackB"]["phase"] or report.get("readOnly") is not True:
        raise ConvergenceError("invalid Track B convergence report")
    if report.get("trackBClosed") is not True:
        raise ConvergenceError("Track B is not closed")
    if report.get("status") != baseline["trackB"]["requiredStatus"]:
        raise ConvergenceError(f"Track B drift remains: {report.get('status')}")
    handoff = report.get("handoff")
    if not isinstance(handoff, dict) or handoff.get("required") is not False:
        raise ConvergenceError("Track B has unresolved drift handoff")
    adoption = report.get("adoption")
    if not isinstance(adoption, dict) or adoption.get("adoptionPerformed") is not False:
        raise ConvergenceError("Track B convergence cannot perform adoption")
    safety = report.get("safety")
    if not isinstance(safety, dict) or any(bool(value) for value in safety.values()):
        raise ConvergenceError("Track B safety boundary changed")


def validate_track_c_monitor(report: dict[str, Any], baseline: dict[str, Any]) -> None:
    track_c = baseline["trackC"]
    if report.get("schemaVersion") != 1 or report.get("phase") != track_c["monitorPhase"] or report.get("readOnly") is not True:
        raise ConvergenceError("invalid Track C drift-monitor report")
    if report.get("status") != track_c["requiredMonitorStatus"]:
        raise ConvergenceError(f"unexplained Track C drift remains: {report.get('status')}")
    handoff = report.get("handoff")
    if not isinstance(handoff, dict) or handoff.get("driftRequired") is not False:
        raise ConvergenceError("Track C has unexplained ID parity drift")
    remediation = report.get("remediation")
    if not isinstance(remediation, dict) or remediation.get("remainingRows") != 3:
        raise ConvergenceError("Track C monitor no longer exposes the exact three C5 remediation rows")
    if remediation.get("canonicalIds") != list(EXPECTED_IDS):
        raise ConvergenceError("Track C monitor remediation cohort changed")
    safety = report.get("safety")
    if not isinstance(safety, dict) or any(bool(value) for value in safety.values()):
        raise ConvergenceError("Track C monitor safety boundary changed")


def validate_track_c(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if report.get("schemaVersion") != 1 or report.get("phase") != baseline["trackC"]["phase"] or report.get("readOnly") is not True:
        raise ConvergenceError("invalid Track C closure report")
    if report.get("trackCClosed") is not True or report.get("status") != baseline["trackC"]["requiredStatus"]:
        raise ConvergenceError("Track C is not cleanly closed")
    summary = report.get("summary")
    if not isinstance(summary, dict) or (summary.get("sources"), summary.get("closureResolved"), summary.get("unresolved")) != (3, 3, 0):
        raise ConvergenceError("Track C closure counts changed")
    rows = rows_by_id(report.get("decisions"), "Track C decision")
    if set(rows) != set(EXPECTED_IDS):
        raise ConvergenceError("Track C closure cohort changed")
    for cid, disposition in baseline["expectedTrackCDispositions"].items():
        if rows[cid].get("disposition") != disposition:
            raise ConvergenceError(f"Track C disposition changed for {cid}")
    safety = report.get("safetyBoundary")
    if not isinstance(safety, dict) or any(bool(value) for value in safety.values()):
        raise ConvergenceError("Track C safety boundary changed")
    return rows


def validate_a7(report: dict[str, Any]) -> None:
    if report.get("schemaVersion") != 1 or report.get("phase") != "A7_LKG_SAFETY":
        raise ConvergenceError("invalid A7 LKG report")
    if report.get("status") != "SAFE" or report.get("violations") != []:
        raise ConvergenceError("permanent LKG safety is not SAFE")
    if report.get("mutatesFoundation") is not False or report.get("promotionAttempted") is not False:
        raise ConvergenceError("A7 must remain read-only")


def registry_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if registry.get("schemaVersion") != 1:
        raise ConvergenceError("unsupported Farm registry")
    return rows_by_id(registry.get("sources"), "Farm registry")


def workers_by_id(worker: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if worker.get("schemaVersion") != 2 or not isinstance(worker.get("sources"), dict):
        raise ConvergenceError("unsupported pending worker state")
    return {str(cid): row for cid, row in worker["sources"].items() if isinstance(row, dict)}


def validate_operational_convergence(track_c_rows: dict[str, dict[str, Any]], registry: dict[str, Any], worker: dict[str, Any]) -> list[dict[str, Any]]:
    farm = registry_by_id(registry)
    workers = workers_by_id(worker)
    for cid in EXPECTED_IDS:
        if cid not in farm or cid not in workers:
            raise ConvergenceError(f"live lifecycle authority missing {cid}")

    lumos_source, lumos_worker = farm[LUMOS], workers[LUMOS]
    lumos_providers = sorted(str(value) for value in lumos_source.get("providers", []) if isinstance(value, str))
    lumos_selected = sorted(str(value) for value in lumos_worker.get("selectedProviders", []) if isinstance(value, str))
    if lumos_providers != ["uma"] or lumos_selected != ["uma"] or lumos_worker.get("state") != "APPROVED":
        raise ConvergenceError("Lumos lifecycle no longer converges on approved UMA-only authority")

    manga_decision = track_c_rows[MANGABALL]
    retry_semantics = manga_decision.get("retrySemantics")
    if manga_decision.get("lifecycleCategory") != "SOURCE_PARSER_FAILURE" or not isinstance(retry_semantics, dict):
        raise ConvergenceError("MangaBall C5 retry-lane semantics are missing")
    if retry_semantics.get("terminal") is not False or retry_semantics.get("genericFailThresholdAutoHold") is not False or retry_semantics.get("ownerActionRequired") is not False:
        raise ConvergenceError("MangaBall C5 retry-lane semantics changed")

    manga_worker = workers[MANGABALL]
    if manga_worker.get("state") != "RETRY":
        raise ConvergenceError("MangaBall no longer remains in the non-terminal retry lane")
    worker_failure = manga_worker.get("failureCategory")
    if worker_failure not in {None, "SOURCE_PARSER_FAILURE"}:
        raise ConvergenceError("MangaBall live worker category conflicts with C5 SOURCE_PARSER_FAILURE disposition")
    retry_policy = manga_worker.get("retryPolicy")
    if isinstance(retry_policy, dict) and retry_policy.get("genericFailThresholdAutoHold") is not False:
        raise ConvergenceError("MangaBall retry policy unexpectedly allows generic auto-hold")

    soft_decision = track_c_rows[SOFTKOMIK]
    auth_semantics = soft_decision.get("authSemantics")
    if soft_decision.get("lifecycleCategory") != "AUTH_REQUIRED" or not isinstance(auth_semantics, dict):
        raise ConvergenceError("SoftKomik C5 auth semantics are missing")
    if auth_semantics.get("credentialInjectionAllowed") is not False or auth_semantics.get("autoCredentialProvisioning") is not False or auth_semantics.get("holdCandidate") is not True:
        raise ConvergenceError("SoftKomik C5 auth safety semantics changed")

    soft_worker = workers[SOFTKOMIK]
    if soft_worker.get("state") != "NEEDS_ATTENTION":
        raise ConvergenceError("SoftKomik no longer remains in the owner-action lifecycle lane")
    if soft_worker.get("authType") not in {"TOKEN", "FORM", "COOKIE"}:
        raise ConvergenceError("SoftKomik auth type is no longer explicit")
    if soft_worker.get("authType") != auth_semantics.get("authType"):
        raise ConvergenceError("SoftKomik live auth type diverged from C5 closure")

    return [
        {
            "canonicalId": LUMOS,
            "trackCDisposition": track_c_rows[LUMOS]["disposition"],
            "liveState": lumos_worker.get("state"),
            "providers": lumos_providers,
            "selectedProviders": lumos_selected,
            "converged": True,
        },
        {
            "canonicalId": MANGABALL,
            "trackCDisposition": manga_decision["disposition"],
            "lifecycleCategory": manga_decision.get("lifecycleCategory"),
            "liveState": manga_worker.get("state"),
            "workerFailureCategory": worker_failure,
            "workerEvidencePredatesCorrectedHarness": manga_decision.get("authoritySnapshot", {}).get("workerEvidencePredatesCorrectedHarness"),
            "converged": True,
        },
        {
            "canonicalId": SOFTKOMIK,
            "trackCDisposition": soft_decision["disposition"],
            "lifecycleCategory": soft_decision.get("lifecycleCategory"),
            "liveState": soft_worker.get("state"),
            "authType": soft_worker.get("authType"),
            "converged": True,
        },
    ]


def validate_automation_presence(presence: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    required = baseline["permanentAutomation"]
    missing = []
    for name, path in required.items():
        row = presence.get(name)
        if not isinstance(row, dict) or row.get("path") != path or row.get("exists") is not True:
            missing.append(name)
    if missing:
        raise ConvergenceError("permanent automation missing: " + ", ".join(sorted(missing)))
    return sorted(required)


def build_report(
    baseline: dict[str, Any],
    track_b: dict[str, Any],
    track_c_monitor: dict[str, Any],
    track_c: dict[str, Any],
    a7: dict[str, Any],
    registry: dict[str, Any],
    worker: dict[str, Any],
    automation_presence: dict[str, Any],
    current_refs: dict[str, str],
) -> dict[str, Any]:
    validate_baseline(baseline)
    validate_track_b(track_b, baseline)
    validate_track_c_monitor(track_c_monitor, baseline)
    track_c_rows = validate_track_c(track_c, baseline)
    validate_a7(a7)
    operational = validate_operational_convergence(track_c_rows, registry, worker)
    automation = validate_automation_presence(automation_presence, baseline)

    for key in ("controlHead", "sourceInventory", "compatibilityFarm", "miyorareAmain2"):
        require_sha(current_refs.get(key), f"current {key}")

    planning = baseline["planningRefs"]
    ref_drift = {
        key: planning[key] != current_refs[key]
        for key in ("sourceInventory", "compatibilityFarm", "miyorareAmain2")
    }

    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "readOnly": True,
        "status": "D1_CONVERGENCE_BASELINE_CLEAN",
        "trackDClosed": False,
        "nextStage": NEXT_STAGE,
        "sourcePacksAfterTrackC": baseline["sourcePacksAfterTrackC"],
        "currentRefs": dict(current_refs),
        "planningRefDrift": ref_drift,
        "tracks": {
            "trackB": {"closed": True, "status": track_b["status"], "handoffRequired": False},
            "trackC": {
                "closed": True,
                "monitorStatus": track_c_monitor["status"],
                "status": track_c["status"],
                "operationalHandoffs": track_c["summary"]["operationalHandoffs"],
            },
        },
        "permanentAuthority": {
            "lkgSafety": "SAFE",
            "providerCount": a7.get("providerCount"),
            "activeSourceCount": a7.get("activeSourceCount"),
            "activeMembershipCount": a7.get("activeMembershipCount"),
            "automationPathsVerified": automation,
        },
        "operationalConvergence": operational,
        "transitionalMonitors": list(baseline.get("transitionalMonitors") or []),
        "d2Questions": [
            "prove source-scoped provider preference cannot regress to a failed provider",
            "prove candidate/LKG recovery remains isolated per provider/source",
            "prove stale READY evidence is invalidated after provider-baseline drift",
        ],
        "safety": {
            "mutateFarmAuthority": False,
            "mutateProviderSelection": False,
            "mutateLastKnownGood": False,
            "mutateRetryHeld": False,
            "mutateCanonicalIds": False,
            "mutateConsumerPackaging": False,
            "approveSource": False,
            "dispatchPromotion": False,
            "publishRelease": False,
        },
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track D D1 — B+C Convergence Baseline",
        "",
        f"- Status: `{report['status']}`",
        f"- Track D closed: `{str(report['trackDClosed']).lower()}`",
        f"- Next stage: `{report['nextStage']}`",
        f"- Track B: `{report['tracks']['trackB']['status']}`",
        f"- Track C: `{report['tracks']['trackC']['status']}`",
        f"- LKG safety: `{report['permanentAuthority']['lkgSafety']}`",
        "",
        "## Operational convergence",
        "",
        "| Source | Live state | Category/provider |",
        "|---|---|---|",
    ]
    for row in report["operationalConvergence"]:
        detail = row.get("failureCategory") or row.get("lifecycleCategory") or ",".join(row.get("providers") or [])
        lines.append(f"| `{row['canonicalId']}` | `{row['liveState']}` | `{detail}` |")
    lines.extend(["", "D1 is read-only. It establishes the post-Track-B/C maintenance baseline; provider preference/recovery proof begins in D2.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--track-b-report", required=True)
    parser.add_argument("--track-c-monitor-report", required=True)
    parser.add_argument("--track-c-report", required=True)
    parser.add_argument("--a7-report", required=True)
    parser.add_argument("--farm-registry", required=True)
    parser.add_argument("--worker-state", required=True)
    parser.add_argument("--automation-presence", required=True)
    parser.add_argument("--control-head", required=True)
    parser.add_argument("--inventory-commit", required=True)
    parser.add_argument("--farm-commit", required=True)
    parser.add_argument("--miyorare-commit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    args = parser.parse_args()
    try:
        report = build_report(
            load(args.baseline),
            load(args.track_b_report),
            load(args.track_c_monitor_report),
            load(args.track_c_report),
            load(args.a7_report),
            load(args.farm_registry),
            load(args.worker_state),
            load(args.automation_presence),
            {
                "controlHead": args.control_head,
                "sourceInventory": args.inventory_commit,
                "compatibilityFarm": args.farm_commit,
                "miyorareAmain2": args.miyorare_commit,
            },
        )
        save(args.output, report)
        if args.markdown_output:
            Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (ConvergenceError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
