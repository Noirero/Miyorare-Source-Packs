#!/usr/bin/env python3
"""Track D D3: converge permanent drift sentinels with unified health observability.

D3 does not create lifecycle or promotion authority. It proves that legacy pack membership is
bounded to exact reviewed canonical IDs, live Farm state can move independently, new sources
require explicit pack membership, Track B/C drift sentinels remain read-only handoffs, and P2-A
projects a fail-closed unified health view without mutating canonical identity or LKG.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

PHASE = "TRACK_D_D3_UNIFIED_DRIFT_HEALTH"
NEXT_STAGE = "TRACK_D_D4_LONG_TERM_AUTOMATION_ACCEPTANCE"
D2_PHASE = "TRACK_D_D2_PROVIDER_PREFERENCE_RECOVERY"
D2_STATUS = "D2_PROVIDER_PREFERENCE_RECOVERY_PROVEN"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class D3Error(ValueError):
    pass


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise D3Error(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise D3Error(f"invalid {label} SHA")
    return value


def validate_baseline(baseline: dict[str, Any]) -> None:
    if baseline.get("schemaVersion") != 1 or baseline.get("phase") != PHASE:
        raise D3Error("invalid D3 baseline header")
    if baseline.get("readOnlyAcceptance") is not True:
        raise D3Error("D3 acceptance must be read-only")
    require_sha(baseline.get("sourcePacksAfterD2"), "post-D2 Source-Packs")
    require_sha(baseline.get("compatibilityFarmBaseline"), "D3 Farm baseline")
    require_sha(baseline.get("reviewedPackAuthorityFarmCommit"), "reviewed pack authority Farm")
    artifact = baseline.get("d2Artifact")
    if not isinstance(artifact, dict):
        raise D3Error("D2 artifact binding missing")
    if not isinstance(artifact.get("runId"), int) or not isinstance(artifact.get("artifactId"), int):
        raise D3Error("D2 artifact ids invalid")
    require_sha(artifact.get("headSha"), "D2 artifact head")
    if not isinstance(artifact.get("digest"), str) or not artifact["digest"].startswith("sha256:"):
        raise D3Error("D2 artifact digest invalid")
    if artifact.get("requiredStatus") != D2_STATUS:
        raise D3Error("D3 requires proven D2 result")
    layers = baseline.get("permanentLayers")
    expected_layers = {
        "enDriftWorkflow", "idDriftWorkflow", "unifiedHealthWorkflow",
        "canonicalRegistryTool", "unifiedHealthTool", "onboardingWorkflow",
    }
    if not isinstance(layers, dict) or set(layers) != expected_layers:
        raise D3Error("permanentLayers binding invalid")
    invariants = baseline.get("requiredInvariants")
    if not isinstance(invariants, list) or len(invariants) != 5 or len(invariants) != len(set(invariants)):
        raise D3Error("requiredInvariants binding invalid")
    if baseline.get("nextStage") != NEXT_STAGE:
        raise D3Error("D3 must hand off to D4")


def validate_d2(report: dict[str, Any], baseline: dict[str, Any]) -> None:
    if report.get("schemaVersion") != 1 or report.get("phase") != D2_PHASE:
        raise D3Error("invalid D2 report")
    if report.get("readOnly") is not True or report.get("status") != baseline["d2Artifact"]["requiredStatus"]:
        raise D3Error("D2 provider/recovery acceptance is not proven")
    if report.get("trackDClosed") is not False or report.get("nextStage") != PHASE:
        raise D3Error("D2 does not hand off to D3")
    safety = report.get("safety")
    if not isinstance(safety, dict) or any(bool(value) for value in safety.values()):
        raise D3Error("D2 safety boundary changed")


def require_markers(text: str, markers: list[str], label: str) -> int:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise D3Error(f"{label} markers missing: " + "; ".join(missing))
    return len(markers)


def validate_workflows(
    b4_text: str,
    c4_text: str,
    p2a_text: str,
    onboarding_text: str,
) -> dict[str, Any]:
    counts = {
        "enDrift": require_markers(b4_text, [
            "schedule:",
            "permissions:",
            "contents: read",
            "Track B EN parity drift detected",
            "Existing Source Lab inventory/Farm/PENDING/approval pipeline remains the handoff authority",
        ], "Track B EN drift workflow"),
        "idDrift": require_markers(c4_text, [
            "schedule:",
            "permissions:",
            "contents: read",
            "Track C ID parity drift detected",
            "Existing Source Lab inventory/Farm/PENDING/approval pipeline remains the authority",
        ], "Track C ID drift workflow"),
        "unifiedHealth": require_markers(p2a_text, [
            "schedule:",
            "contents: read",
            "Checkout live Compatibility Farm state",
            "Checkout exact reviewed Farm membership snapshot",
            "--reviewed-farm reviewed-farm/compatibility/source-registry.json",
            "Undeclared pack memberships fail-closed",
        ], "P2-A unified health workflow"),
        "onboarding": require_markers(onboarding_text, [
            "packs:",
            "Explicit comma-separated pack membership",
            "'packs': requested_packs",
            "'packMembershipAuthority': 'owner-explicit-workflow-input'",
        ], "Source Lab onboarding workflow"),
    }
    return {
        "status": "PROVEN",
        "markerCounts": counts,
        "authority": "EXISTING_SOURCE_LAB_PIPELINE",
        "newParallelLifecycleAuthority": False,
    }


def validate_projection(
    canonical: dict[str, Any],
    health: dict[str, Any],
    baseline: dict[str, Any],
    current_refs: dict[str, str],
) -> dict[str, Any]:
    if canonical.get("schemaVersion") != 2 or canonical.get("kind") != "MIYORARE_CANONICAL_SOURCE_REGISTRY":
        raise D3Error("invalid Canonical Source Registry V2 projection")
    migration = canonical.get("migration")
    if not isinstance(migration, dict):
        raise D3Error("canonical migration metadata missing")
    if migration.get("reviewedFarmCommit") != baseline["reviewedPackAuthorityFarmCommit"]:
        raise D3Error("reviewed pack authority binding changed")
    if migration.get("liveFarmCommit") != current_refs["compatibilityFarm"]:
        raise D3Error("canonical projection is not bound to the D3 live Farm")
    if migration.get("reviewedSourceBoundAuthority") is not True:
        raise D3Error("legacy pack authority is not exact-source bounded")
    if migration.get("languageInferenceDisabled") is not True:
        raise D3Error("language inference was re-enabled")
    if migration.get("packMembershipAuthority") != "source-declaration-or-exact-reviewed-source-authority":
        raise D3Error("canonical pack authority semantics changed")

    canonical_sources = canonical.get("sources")
    health_sources = health.get("sources")
    if not isinstance(canonical_sources, list) or not isinstance(health_sources, list):
        raise D3Error("projection source lists missing")
    if health.get("schemaVersion") != 1 or health.get("kind") != "MIYORARE_UNIFIED_SOURCE_HEALTH":
        raise D3Error("invalid unified health projection")
    cindex = {row.get("canonicalId"): row for row in canonical_sources if isinstance(row, dict)}
    hindex = {row.get("canonicalId"): row for row in health_sources if isinstance(row, dict)}
    if len(cindex) != len(canonical_sources) or len(hindex) != len(health_sources) or set(cindex) != set(hindex):
        raise D3Error("canonical/unified health identity sets differ")

    undeclared: list[str] = []
    explicit = 0
    reviewed = 0
    for cid, row in sorted(cindex.items()):
        if not isinstance(cid, str):
            raise D3Error("invalid canonical identity in D3 projection")
        packs = row.get("packs")
        if not isinstance(packs, list):
            raise D3Error(f"{cid}: packs missing")
        authority = row.get("packAuthority")
        if packs:
            if authority == "source-declaration":
                explicit += 1
            elif authority == "reviewed-existing-source-authority":
                reviewed += 1
            else:
                raise D3Error(f"{cid}: populated packs lack valid authority")
        else:
            undeclared.append(cid)
            if authority != "undeclared":
                raise D3Error(f"{cid}: empty packs not marked undeclared")
            if row.get("lifecycle", {}).get("state") != "held":
                raise D3Error(f"{cid}: undeclared packs not held")
            if row.get("compatibility", {}).get("health") != "HELD":
                raise D3Error(f"{cid}: undeclared packs not HEALTH=HELD")
            hrow = hindex[cid]
            if hrow.get("health") != "HELD" or "PACK_MEMBERSHIP_UNDECLARED" not in hrow.get("reasonCodes", []):
                raise D3Error(f"{cid}: unified health did not surface pack authority handoff")
        if hindex[cid].get("packs") != packs:
            raise D3Error(f"{cid}: unified health packs diverged from canonical authority")

    declared_by_metadata = migration.get("undeclaredPackMembership")
    if sorted(undeclared) != sorted(declared_by_metadata or []):
        raise D3Error("canonical undeclared membership metadata diverged")
    if migration.get("undeclaredPackMembershipCount") != len(undeclared):
        raise D3Error("canonical undeclared membership count diverged")
    health_counts = dict(sorted(Counter(str(row.get("health")) for row in health_sources).items()))
    return {
        "status": "PROVEN",
        "sourceCount": len(canonical_sources),
        "reviewedExistingSourceAuthorityCount": reviewed,
        "explicitSourceDeclarationCount": explicit,
        "undeclaredPackMembershipCount": len(undeclared),
        "ownerPackAuthorityHandoffs": sorted(undeclared),
        "healthCounts": health_counts,
    }


def build_report(
    baseline: dict[str, Any],
    d2: dict[str, Any],
    canonical: dict[str, Any],
    health: dict[str, Any],
    workflow_texts: dict[str, str],
    current_refs: dict[str, str],
) -> dict[str, Any]:
    validate_baseline(baseline)
    validate_d2(d2, baseline)
    require_sha(current_refs.get("controlHead"), "D3 control head")
    require_sha(current_refs.get("compatibilityFarm"), "D3 compatibility Farm")
    if current_refs["compatibilityFarm"] != baseline["compatibilityFarmBaseline"]:
        raise D3Error("Compatibility Farm moved after D3 planning")
    projection = validate_projection(canonical, health, baseline, current_refs)
    workflow_proof = validate_workflows(
        workflow_texts["enDriftWorkflow"], workflow_texts["idDriftWorkflow"],
        workflow_texts["unifiedHealthWorkflow"], workflow_texts["onboardingWorkflow"],
    )
    handoffs = projection["undeclaredPackMembershipCount"]
    status = "D3_UNIFIED_DRIFT_HEALTH_PROVEN" if handoffs == 0 else "D3_UNIFIED_DRIFT_HEALTH_PROVEN_WITH_OWNER_PACK_HANDOFFS"
    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "readOnlyAcceptance": True,
        "status": status,
        "trackDClosed": False,
        "nextStage": NEXT_STAGE,
        "currentRefs": dict(current_refs),
        "proofs": {
            "packAuthorityContinuity": projection,
            "driftAndHealthConvergence": workflow_proof,
            "unifiedHealthObservability": {
                "status": "PROVEN",
                "scheduled": True,
                "mutatesAuthority": False,
                "sourceCount": projection["sourceCount"],
                "healthCounts": projection["healthCounts"],
            },
            "futureOnboardingPackAuthority": {
                "status": "PROVEN",
                "explicitPackMembershipRequired": True,
                "languageInference": False,
                "canonicalPrefixInferenceForNewSources": False,
            },
        },
        "operationalHandoffs": {
            "ownerPackAuthorityRequired": projection["ownerPackAuthorityHandoffs"],
            "count": handoffs,
            "note": "Existing live sources absent from the legacy reviewed snapshot remain fail-closed until explicit pack membership is authorized; D3 does not infer or mutate those memberships.",
        },
        "safety": {
            "mutateCanonicalIds": False,
            "mutateProviderSelection": False,
            "mutateFarmLifecycle": False,
            "mutateLastKnownGood": False,
            "mutateRetryHeld": False,
            "approveOrPromote": False,
            "mutateConsumerPackaging": False,
            "publishRelease": False,
            "inferPackFromLanguage": False,
            "inferNewPackFromCanonicalPrefix": False,
        },
    }


def markdown(report: dict[str, Any]) -> str:
    projection = report["proofs"]["packAuthorityContinuity"]
    lines = [
        "# Track D — D3 Unified Drift & Health",
        "",
        f"- Status: `{report['status']}`",
        f"- Sources projected: **{projection['sourceCount']}**",
        f"- Reviewed-existing pack authority: **{projection['reviewedExistingSourceAuthorityCount']}**",
        f"- Explicit source pack declarations: **{projection['explicitSourceDeclarationCount']}**",
        f"- Owner pack-authority handoffs: **{projection['undeclaredPackMembershipCount']}**",
        f"- Health counts: `{projection['healthCounts']}`",
        f"- Next: `{report['nextStage']}`",
        "",
        "D3 is observational/convergent only. It does not select providers, change LKG, mutate Retry/Held, approve/promote, rewrite consumer packs, or publish.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--d2-report", required=True)
    parser.add_argument("--canonical-registry", required=True)
    parser.add_argument("--unified-health", required=True)
    parser.add_argument("--en-drift-workflow", required=True)
    parser.add_argument("--id-drift-workflow", required=True)
    parser.add_argument("--unified-health-workflow", required=True)
    parser.add_argument("--onboarding-workflow", required=True)
    parser.add_argument("--control-head", required=True)
    parser.add_argument("--farm-commit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()
    report = build_report(
        load(args.baseline),
        load(args.d2_report),
        load(args.canonical_registry),
        load(args.unified_health),
        {
            "enDriftWorkflow": Path(args.en_drift_workflow).read_text(encoding="utf-8"),
            "idDriftWorkflow": Path(args.id_drift_workflow).read_text(encoding="utf-8"),
            "unifiedHealthWorkflow": Path(args.unified_health_workflow).read_text(encoding="utf-8"),
            "onboardingWorkflow": Path(args.onboarding_workflow).read_text(encoding="utf-8"),
        },
        {"controlHead": args.control_head, "compatibilityFarm": args.farm_commit},
    )
    save(args.output, report)
    Path(args.markdown_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
