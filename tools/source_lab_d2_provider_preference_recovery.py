#!/usr/bin/env python3
"""Track D D2: prove provider preference, scoped recovery, and stale-evidence invalidation.

D2 is read-only. It binds clean D1 convergence to the live Compatibility Farm, reuses the
permanent A7 LKG audit, checks live authority, and requires behavioral proofs from production
lifecycle tests. Historical provider-wide onboarding approvals are recorded but are not treated
as partial-provider authority unless they carry both activeProviders and heldProviders.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PHASE = "TRACK_D_D2_PROVIDER_PREFERENCE_RECOVERY"
NEXT_STAGE = "TRACK_D_D3_UNIFIED_DRIFT_HEALTH"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LUMOS = "miyorare:inventory-id:LUMOSKOMIK"
READY = "READY_FOR_APPROVAL"


class D2Error(ValueError):
    pass


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise D2Error(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise D2Error(f"invalid {label} SHA")
    return value


def validate_baseline(baseline: dict[str, Any]) -> None:
    if baseline.get("schemaVersion") != 1 or baseline.get("phase") != PHASE or baseline.get("readOnly") is not True:
        raise D2Error("invalid D2 baseline header")
    require_sha(baseline.get("sourcePacksAfterD1"), "post-D1 Source-Packs")
    require_sha(baseline.get("compatibilityFarmBaseline"), "D2 Farm baseline")
    artifact = baseline.get("d1Artifact")
    if not isinstance(artifact, dict):
        raise D2Error("D1 artifact binding missing")
    if not isinstance(artifact.get("runId"), int) or not isinstance(artifact.get("artifactId"), int):
        raise D2Error("D1 artifact ids invalid")
    require_sha(artifact.get("headSha"), "D1 artifact head")
    if not isinstance(artifact.get("name"), str) or not artifact["name"]:
        raise D2Error("D1 artifact name missing")
    if not isinstance(artifact.get("digest"), str) or not artifact["digest"].startswith("sha256:"):
        raise D2Error("D1 artifact digest invalid")
    if artifact.get("requiredStatus") != "D1_CONVERGENCE_BASELINE_CLEAN":
        raise D2Error("D2 requires clean D1 convergence")
    proofs = baseline.get("requiredBehaviorProofs")
    if not isinstance(proofs, list) or not proofs or len(proofs) != len(set(proofs)):
        raise D2Error("requiredBehaviorProofs invalid")
    files = baseline.get("authorityFiles")
    if not isinstance(files, dict) or set(files) != {
        "workerTool", "approvalTool", "promotionWorkflow", "farmApprovalTool", "farmPromotionTool"
    }:
        raise D2Error("authorityFiles binding invalid")
    required_lumos = baseline.get("requiredLumosAuthority")
    if not isinstance(required_lumos, dict) or required_lumos.get("canonicalId") != LUMOS:
        raise D2Error("required Lumos authority missing")
    if baseline.get("nextStage") != NEXT_STAGE:
        raise D2Error("D2 next stage must be D3 unified drift/health")


def validate_d1(report: dict[str, Any], baseline: dict[str, Any]) -> None:
    artifact = baseline["d1Artifact"]
    if report.get("schemaVersion") != 1 or report.get("phase") != "TRACK_D_D1_CONVERGENCE_BASELINE":
        raise D2Error("invalid D1 report")
    if report.get("readOnly") is not True or report.get("status") != artifact["requiredStatus"]:
        raise D2Error("D1 convergence is not clean")
    if report.get("trackDClosed") is not False or report.get("nextStage") != PHASE:
        raise D2Error("D1 does not hand off to D2")
    expected = {
        "prove source-scoped provider preference cannot regress to a failed provider",
        "prove candidate/LKG recovery remains isolated per provider/source",
        "prove stale READY evidence is invalidated after provider-baseline drift",
    }
    questions = report.get("d2Questions")
    if not isinstance(questions, list) or set(questions) != expected:
        raise D2Error("D1 D2-question binding changed")
    authority = report.get("permanentAuthority")
    if not isinstance(authority, dict) or authority.get("lkgSafety") != "SAFE":
        raise D2Error("D1 permanent LKG authority was not SAFE")
    safety = report.get("safety")
    if not isinstance(safety, dict) or any(bool(value) for value in safety.values()):
        raise D2Error("D1 safety boundary changed")


def validate_a7(report: dict[str, Any]) -> None:
    if report.get("schemaVersion") != 1 or report.get("phase") != "A7_LKG_SAFETY":
        raise D2Error("invalid A7 report")
    if report.get("status") != "SAFE" or report.get("violations") != []:
        raise D2Error("A7 LKG safety is not SAFE")
    if report.get("mutatesFoundation") is not False or report.get("promotionAttempted") is not False:
        raise D2Error("A7 must remain read-only")


def source_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if registry.get("schemaVersion") != 1 or not isinstance(registry.get("sources"), list):
        raise D2Error("unsupported Farm source registry")
    result: dict[str, dict[str, Any]] = {}
    for row in registry["sources"]:
        if not isinstance(row, dict) or not isinstance(row.get("canonicalId"), str):
            continue
        cid = row["canonicalId"]
        if cid in result:
            raise D2Error(f"duplicate Farm source: {cid}")
        result[cid] = row
    return result


def worker_map(worker: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if worker.get("schemaVersion") != 2 or not isinstance(worker.get("sources"), dict):
        raise D2Error("unsupported pending worker state")
    return {str(cid): row for cid, row in worker["sources"].items() if isinstance(row, dict)}


def validate_provider_preference(registry: dict[str, Any], worker: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    sources = source_map(registry)
    workers = worker_map(worker)
    lumos = sources.get(LUMOS)
    lumos_worker = workers.get(LUMOS)
    required = baseline["requiredLumosAuthority"]
    if not isinstance(lumos, dict) or not isinstance(lumos_worker, dict):
        raise D2Error("Lumos live authority missing")
    providers = sorted(str(v) for v in lumos.get("providers", []) if isinstance(v, str))
    selected = sorted(str(v) for v in lumos_worker.get("selectedProviders", []) if isinstance(v, str))
    if providers != required["providers"] or selected != required["selectedProviders"] or lumos_worker.get("state") != required["workerState"]:
        raise D2Error("Lumos provider preference regressed from approved UMA-only authority")

    scoped_rows: list[dict[str, Any]] = []
    legacy_rows: list[str] = []
    for cid, source in sorted(sources.items()):
        enrollment = source.get("compatibilityEnrollment")
        if not isinstance(enrollment, dict) or enrollment.get("state") != "ACTIVE":
            continue
        approval = source.get("onboardingApproval")
        if not isinstance(approval, dict):
            continue
        if approval.get("state") != "APPROVED":
            raise D2Error(f"{cid} onboardingApproval is not APPROVED")

        has_active = "activeProviders" in approval
        has_held = "heldProviders" in approval
        if not has_active and not has_held:
            # Historical/provider-wide approval format. A7 remains the global LKG/candidate-leak proof;
            # partial-provider invariants only apply when the scoped authority fields are present.
            legacy_rows.append(cid)
            continue
        if has_active != has_held:
            raise D2Error(f"{cid} onboarding provider authority malformed")

        active = approval.get("activeProviders")
        held = approval.get("heldProviders")
        source_providers = source.get("providers")
        if not isinstance(active, list) or not active or not isinstance(held, list) or not isinstance(source_providers, list):
            raise D2Error(f"{cid} onboarding provider authority malformed")
        active_set = set(active)
        provider_set = set(source_providers)
        held_set = {
            item.get("provider")
            for item in held
            if isinstance(item, dict) and isinstance(item.get("provider"), str)
        }
        if len(active_set) != len(active) or provider_set != active_set:
            raise D2Error(f"{cid} active provider set diverged from onboarding approval")
        if held_set & provider_set:
            raise D2Error(f"{cid} held provider re-entered active authority")
        current = source.get("currentVersion")
        lkg = source.get("lastKnownGood")
        if not isinstance(current, dict) or not isinstance(lkg, dict):
            raise D2Error(f"{cid} active version maps malformed")
        for provider in provider_set:
            if not isinstance(current.get(provider), str) or current.get(provider) != lkg.get(provider):
                raise D2Error(f"{cid}@{provider} current/LKG authority diverged")
        identities = source.get("upstreamIdentities")
        if isinstance(identities, dict):
            if not provider_set.issubset(identities):
                raise D2Error(f"{cid} active provider identity missing")
            if held_set & set(identities):
                raise D2Error(f"{cid} held provider identity was reintroduced")
        scoped_rows.append({
            "canonicalId": cid,
            "activeProviders": sorted(provider_set),
            "heldProviders": sorted(value for value in held_set if isinstance(value, str)),
        })

    return {
        "status": "PROVEN",
        "lumosProviders": providers,
        "lumosSelectedProviders": selected,
        "scopedApprovedSources": scoped_rows,
        "scopedApprovedSourceCount": len(scoped_rows),
        "legacyProviderWideApprovals": sorted(legacy_rows),
        "legacyProviderWideApprovalCount": len(legacy_rows),
    }


def validate_ready_evidence(registry: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any]:
    provider_baselines = registry.get("providerBaselines")
    if not isinstance(provider_baselines, dict):
        raise D2Error("Farm providerBaselines missing")
    sources = source_map(registry)
    workers = worker_map(worker)
    ready_rows: list[dict[str, Any]] = []
    for cid, entry in sorted(workers.items()):
        if entry.get("state") != READY:
            continue
        source = sources.get(cid)
        enrollment = source.get("compatibilityEnrollment") if isinstance(source, dict) else None
        if not isinstance(source, dict) or not isinstance(enrollment, dict) or enrollment.get("state") != "PENDING":
            raise D2Error(f"READY source is not live PENDING authority: {cid}")
        selected = entry.get("selectedProviders")
        tested = entry.get("testedVersions")
        if not isinstance(selected, list) or not selected or len(set(selected)) != len(selected):
            raise D2Error(f"{cid} READY selectedProviders invalid")
        if not isinstance(tested, dict) or set(tested) != set(selected):
            raise D2Error(f"{cid} READY testedVersions binding invalid")
        for provider in selected:
            if provider_baselines.get(provider) != tested.get(provider):
                raise D2Error(f"{cid} stale READY evidence survived provider-baseline drift")
        if entry.get("approvalState") != "WAITING_FOR_APPROVAL" or entry.get("publishEligible") is not False:
            raise D2Error(f"{cid} READY authority state invalid")
        ready_rows.append({"canonicalId": cid, "providers": sorted(selected), "testedVersions": dict(sorted(tested.items()))})
    return {"status": "PROVEN", "liveReadyCount": len(ready_rows), "liveReady": ready_rows}


def validate_behavior_proofs(manifest: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("proofs"), dict):
        raise D2Error("behavior proof manifest invalid")
    proofs = manifest["proofs"]
    missing: list[str] = []
    failed: list[str] = []
    for name in baseline["requiredBehaviorProofs"]:
        row = proofs.get(name)
        if not isinstance(row, dict):
            missing.append(name)
        elif row.get("passed") is not True:
            failed.append(name)
    if missing:
        raise D2Error("behavior proof missing: " + ", ".join(sorted(missing)))
    if failed:
        raise D2Error("behavior proof failed: " + ", ".join(sorted(failed)))
    return {"status": "PROVEN", "proofs": sorted(baseline["requiredBehaviorProofs"])}


def require_markers(text: str, markers: list[str], label: str) -> int:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise D2Error(f"{label} invariant markers missing: " + "; ".join(missing))
    return len(markers)


def validate_authority_code(worker_text: str, approval_text: str, promotion_text: str, farm_approval_text: str, farm_promotion_text: str) -> dict[str, Any]:
    counts = {
        "worker": require_markers(worker_text, [
            "def ready_evidence_is_stale(", "def invalidate_stale_ready(", 'entry["state"] = RETRY',
            'entry["approvalState"] = "NOT_READY"', 'entry["revalidationReason"] = "PROVIDER_BASELINE_CHANGED"',
            "baseline_reset = is_retry and retry_evidence_is_stale",
        ], "pending worker"),
        "approval": require_markers(approval_text, [
            'source["providers"] = list(active_providers)', 'source["upstreamIdentities"] = {',
            'source["onboardingApproval"] = {', '"activeProviders": list(active_providers)',
            '"heldProviders": item["heldProviders"]', 'raise ValueError("approval plan changed; refusing stale approval")',
        ], "pending approval"),
        "promotionWorkflow": require_markers(promotion_text, [
            "approval sourceScope changed", "scoped source is not a {provider} member", "source state moved",
            "active/LKG moved", 'entry["state"] = "RETRY"',
            'entry["revalidationReason"] = "PROVIDER_BASELINE_CHANGED"', 'entry["invalidatedByPromotionRunId"]',
            "Refuse promotion if foundation moved after validation",
        ], "promotion workflow"),
        "farmApproval": require_markers(farm_approval_text, [
            "def validate_source_scope(", "approval sourceScope does not match pending candidate",
            "registry changed after staging; approval is stale",
        ], "Farm approval authority"),
        "farmPromotion": require_markers(farm_promotion_text, [
            "authorization sourceScope does not match requested/pending sourceScope",
            "registry lastKnownGood changed after authorization; approval is stale", "Source-level LKG mutation is",
        ], "Farm promotion authority"),
    }
    return {"status": "PROVEN", "markerCounts": counts}


def build_report(baseline: dict[str, Any], d1: dict[str, Any], a7: dict[str, Any], registry: dict[str, Any], worker: dict[str, Any], proof_manifest: dict[str, Any], authority_code: dict[str, str], current_refs: dict[str, str]) -> dict[str, Any]:
    validate_baseline(baseline)
    validate_d1(d1, baseline)
    validate_a7(a7)
    for key in ("controlHead", "compatibilityFarm"):
        require_sha(current_refs.get(key), f"current {key}")
    if current_refs["compatibilityFarm"] != baseline["compatibilityFarmBaseline"]:
        raise D2Error("Compatibility Farm moved from the D2 planning baseline")

    preference = validate_provider_preference(registry, worker, baseline)
    stale_ready = validate_ready_evidence(registry, worker)
    behavior = validate_behavior_proofs(proof_manifest, baseline)
    code = validate_authority_code(
        authority_code["workerTool"], authority_code["approvalTool"], authority_code["promotionWorkflow"],
        authority_code["farmApprovalTool"], authority_code["farmPromotionTool"],
    )
    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "readOnly": True,
        "status": "D2_PROVIDER_PREFERENCE_RECOVERY_PROVEN",
        "trackDClosed": False,
        "nextStage": NEXT_STAGE,
        "currentRefs": dict(current_refs),
        "proofs": {
            "providerPreference": preference,
            "candidateLkgRecoveryIsolation": {
                "status": "PROVEN",
                "a7Status": a7["status"],
                "behaviorProofs": behavior["proofs"],
                "authorityCode": code,
            },
            "staleReadyInvalidation": stale_ready,
        },
        "safety": {
            "mutateFarmAuthority": False,
            "mutateProviderSelection": False,
            "mutateLastKnownGood": False,
            "mutateRetryHeld": False,
            "approveSource": False,
            "dispatchPromotion": False,
            "mutateCanonicalIds": False,
            "mutateConsumerPackaging": False,
            "publishRelease": False,
        },
    }


def markdown(report: dict[str, Any]) -> str:
    preference = report["proofs"]["providerPreference"]
    stale = report["proofs"]["staleReadyInvalidation"]
    return "\n".join([
        "# Track D D2 — Provider Preference & Recovery", "",
        f"- Status: `{report['status']}`",
        f"- Track D closed: `{str(report['trackDClosed']).lower()}`",
        f"- Next stage: `{report['nextStage']}`",
        f"- Lumos live providers: `{','.join(preference['lumosProviders'])}`",
        f"- Scoped partial-provider approvals checked: `{preference['scopedApprovedSourceCount']}`",
        f"- Historical/provider-wide approvals recorded: `{preference['legacyProviderWideApprovalCount']}`",
        f"- Live READY entries checked for stale evidence: `{stale['liveReadyCount']}`",
        "- A7 LKG safety: `SAFE`", "",
        "D2 is read-only. Scoped provider preference, recovery/LKG isolation, and stale READY invalidation are proven without changing lifecycle authority.", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--d1-report", required=True)
    parser.add_argument("--a7-report", required=True)
    parser.add_argument("--farm-registry", required=True)
    parser.add_argument("--worker-state", required=True)
    parser.add_argument("--proof-manifest", required=True)
    parser.add_argument("--worker-tool", required=True)
    parser.add_argument("--approval-tool", required=True)
    parser.add_argument("--promotion-workflow", required=True)
    parser.add_argument("--farm-approval-tool", required=True)
    parser.add_argument("--farm-promotion-tool", required=True)
    parser.add_argument("--control-head", required=True)
    parser.add_argument("--farm-commit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    args = parser.parse_args()
    try:
        report = build_report(
            load(args.baseline), load(args.d1_report), load(args.a7_report), load(args.farm_registry),
            load(args.worker_state), load(args.proof_manifest),
            {
                "workerTool": Path(args.worker_tool).read_text(encoding="utf-8"),
                "approvalTool": Path(args.approval_tool).read_text(encoding="utf-8"),
                "promotionWorkflow": Path(args.promotion_workflow).read_text(encoding="utf-8"),
                "farmApprovalTool": Path(args.farm_approval_tool).read_text(encoding="utf-8"),
                "farmPromotionTool": Path(args.farm_promotion_tool).read_text(encoding="utf-8"),
            },
            {"controlHead": args.control_head, "compatibilityFarm": args.farm_commit},
        )
        save(args.output, report)
        if args.markdown_output:
            Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (D2Error, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
