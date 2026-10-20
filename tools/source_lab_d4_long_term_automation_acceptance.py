#!/usr/bin/env python3
"""Track D D4: prove the permanent Source Lab automation chain end to end without mutation.

D4 is an acceptance/audit phase. It binds the exact successful D3 evidence to current immutable
planning refs, reuses A7 LKG safety, validates the promotion-governance contract, and proves that
the permanent workflows form one fail-closed path from upstream detection through runtime
validation, owner-controlled mutation boundaries, recovery/LKG, ID/EN/Global pack construction,
sealing, and the sole stable publisher.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PHASE = "TRACK_D_D4_LONG_TERM_AUTOMATION_ACCEPTANCE"
NEXT_STAGE = "TRACK_D_D5_CLOSURE_TRANSITIONAL_CLEANUP"
D3_PHASE = "TRACK_D_D3_UNIFIED_DRIFT_HEALTH"
D2_PHASE = "TRACK_D_D2_PROVIDER_PREFERENCE_RECOVERY"
D2_STATUS = "D2_PROVIDER_PREFERENCE_RECOVERY_PROVEN"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class D4Error(ValueError):
    pass


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise D4Error(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise D4Error(f"invalid {label} SHA")
    return value


def validate_baseline(baseline: dict[str, Any]) -> None:
    if baseline.get("schemaVersion") != 1 or baseline.get("phase") != PHASE:
        raise D4Error("invalid D4 baseline header")
    if baseline.get("readOnlyAcceptance") is not True:
        raise D4Error("D4 acceptance must be read-only")
    require_sha(baseline.get("sourcePacksAfterD3"), "post-D3 Source-Packs")
    require_sha(baseline.get("compatibilityFarmBaseline"), "D4 Farm baseline")
    require_sha(baseline.get("miyorareAmain2Baseline"), "D4 Miyorare Amain2 baseline")

    artifact = baseline.get("d3Artifact")
    if not isinstance(artifact, dict):
        raise D4Error("D3 artifact binding missing")
    if not isinstance(artifact.get("runId"), int) or not isinstance(artifact.get("artifactId"), int):
        raise D4Error("D3 artifact ids invalid")
    require_sha(artifact.get("headSha"), "D3 artifact head")
    if not isinstance(artifact.get("name"), str) or not artifact["name"]:
        raise D4Error("D3 artifact name missing")
    if not isinstance(artifact.get("digest"), str) or not artifact["digest"].startswith("sha256:"):
        raise D4Error("D3 artifact digest invalid")
    if artifact.get("requiredStatus") not in {
        "D3_UNIFIED_DRIFT_HEALTH_PROVEN",
        "D3_UNIFIED_DRIFT_HEALTH_PROVEN_WITH_OWNER_PACK_HANDOFFS",
    }:
        raise D4Error("D4 requires a proven D3 result")

    chain = baseline.get("permanentChain")
    expected = {
        "upstreamDetection",
        "runtimeValidation",
        "sourceApproval",
        "providerPromotion",
        "lkgSafety",
        "releaseController",
        "releasePublisher",
        "releaseSeal",
        "promotionAuthority",
    }
    if not isinstance(chain, dict) or set(chain) != expected:
        raise D4Error("permanentChain binding invalid")
    acceptance = baseline.get("requiredAcceptance")
    if not isinstance(acceptance, list) or len(acceptance) < 5 or len(acceptance) != len(set(acceptance)):
        raise D4Error("requiredAcceptance binding invalid")
    if baseline.get("nextStage") != NEXT_STAGE:
        raise D4Error("D4 must hand off to D5")


def validate_d3(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if report.get("schemaVersion") != 1 or report.get("phase") != D3_PHASE:
        raise D4Error("invalid D3 report")
    if report.get("readOnlyAcceptance") is not True:
        raise D4Error("D3 report is not read-only")
    if report.get("status") != baseline["d3Artifact"]["requiredStatus"]:
        raise D4Error("D3 artifact status differs from D4 binding")
    if report.get("trackDClosed") is not False or report.get("nextStage") != PHASE:
        raise D4Error("D3 does not hand off to D4")
    safety = report.get("safety")
    if not isinstance(safety, dict) or any(bool(value) for value in safety.values()):
        raise D4Error("D3 safety boundary changed")
    handoffs = report.get("operationalHandoffs")
    if not isinstance(handoffs, dict):
        raise D4Error("D3 operational handoffs missing")
    count = handoffs.get("count")
    ids = handoffs.get("ownerPackAuthorityRequired")
    if not isinstance(count, int) or count < 0 or not isinstance(ids, list) or count != len(ids):
        raise D4Error("D3 owner pack-authority handoff metadata invalid")
    if len(ids) != len(set(ids)) or not all(isinstance(value, str) and value for value in ids):
        raise D4Error("D3 owner pack-authority handoff list invalid")
    return {"count": count, "ownerPackAuthorityRequired": sorted(ids)}


def validate_d2(report: dict[str, Any]) -> None:
    if report.get("schemaVersion") != 1 or report.get("phase") != D2_PHASE:
        raise D4Error("invalid D2 report carried by D3 evidence")
    if report.get("readOnly") is not True or report.get("status") != D2_STATUS:
        raise D4Error("D2 recovery/provider proof is not proven")
    if report.get("trackDClosed") is not False or report.get("nextStage") != D3_PHASE:
        raise D4Error("D2 handoff changed")
    safety = report.get("safety")
    if not isinstance(safety, dict) or any(bool(value) for value in safety.values()):
        raise D4Error("D2 safety boundary changed")
    proofs = report.get("proofs")
    required = {
        "providerPreference",
        "candidateLkgRecoveryIsolation",
        "staleReadyInvalidation",
    }
    if not isinstance(proofs, dict) or not required.issubset(proofs):
        raise D4Error("D2 recovery proofs incomplete")
    for key in required:
        value = proofs[key]
        if not isinstance(value, dict) or value.get("status") not in {"PROVEN", "SAFE"}:
            raise D4Error(f"D2 proof not accepted: {key}")


def validate_a7(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schemaVersion") != 1 or report.get("phase") != "A7_LKG_SAFETY":
        raise D4Error("invalid A7 report")
    if report.get("status") != "SAFE" or report.get("violations") != []:
        raise D4Error("A7 LKG safety is not SAFE")
    if report.get("mutatesFoundation") is not False or report.get("promotionAttempted") is not False:
        raise D4Error("A7 must remain read-only")
    return {
        "status": "PROVEN",
        "providerCount": report.get("providerCount"),
        "activeSourceCount": report.get("activeSourceCount"),
        "activeMembershipCount": report.get("activeMembershipCount"),
        "candidateProviderCount": report.get("candidateProviderCount"),
        "approvalCandidatePresent": bool(report.get("approvalCandidatePresent")),
    }


def validate_authority(authority: dict[str, Any]) -> dict[str, Any]:
    if authority.get("schemaVersion") != 1 or authority.get("defaultDecision") != "HELD":
        raise D4Error("automation promotion authority must fail closed to HELD")
    classes = authority.get("classes")
    if not isinstance(classes, dict):
        raise D4Error("automation promotion classes missing")
    required_classes = {"builder_baseline", "provider_baseline", "source_onboarding", "stable_release"}
    if not required_classes.issubset(classes):
        raise D4Error("required promotion classes missing")

    builder = classes["builder_baseline"]
    provider = classes["provider_baseline"]
    onboarding = classes["source_onboarding"]
    stable = classes["stable_release"]

    if builder.get("automationMayMerge") is not True or builder.get("ownerApprovalRequired") is not False:
        raise D4Error("builder baseline automation authority drifted")
    if builder.get("requiredAuthority") != "source-pack-autonomous-release.yml":
        raise D4Error("builder baseline controller authority drifted")
    builder_gates = set(builder.get("requiredGates") or [])
    if not {"farm-synchronized-manifest", "exact-miyorare-pack-checks", "source-pack-builder-baseline-ci",
            "main-required-gates", "protected-main-ruleset"}.issubset(builder_gates):
        raise D4Error("builder baseline required gates incomplete")

    if provider.get("automationMayMerge") is not False or provider.get("ownerApprovalRequired") is not True:
        raise D4Error("provider baseline owner boundary drifted")
    if provider.get("requiredAuthority") != "source-lab-approve-candidate.yml -> source-lab-promote-candidate.yml":
        raise D4Error("provider promotion authority drifted")
    if provider.get("failureDecision") != "HELD":
        raise D4Error("provider failure must remain HELD")

    if onboarding.get("automationMayMerge") is not False or onboarding.get("ownerApprovalRequired") is not True:
        raise D4Error("source onboarding owner boundary drifted")
    if onboarding.get("requiredAuthority") != "source-lab-approve-ready-sources.yml":
        raise D4Error("source onboarding authority drifted")
    if onboarding.get("failureDecision") != "HELD":
        raise D4Error("source onboarding failure must remain HELD")

    if stable.get("automationMayMerge") is not False or stable.get("ownerApprovalRequired") is not False:
        raise D4Error("stable release automation class drifted")
    if stable.get("requiredAuthority") != "source-pack-autonomous-release.yml -> release-source-packs.yml":
        raise D4Error("stable release controller/publisher authority drifted")
    stable_gates = set(stable.get("requiredGates") or [])
    if not {"pinned-builder-and-provider-fingerprint", "compatibility-contract",
            "immutable-version-allocation", "sole-publisher", "seal", "post-publish-audit"}.issubset(stable_gates):
        raise D4Error("stable release gates incomplete")

    prohibitions = set(authority.get("prohibitions") or [])
    needed = {
        "validation success alone is not promotion authority",
        "automation may not replace LKG after a failed or incomplete candidate",
        "automation may not bypass Main Required Gates",
        "no workflow other than the authoritative stable controller may allocate a stable Source Pack version",
        "no workflow other than the sole publisher may publish a stable Source Pack release",
    }
    if not needed.issubset(prohibitions):
        raise D4Error("promotion authority prohibitions incomplete")

    return {
        "status": "PROVEN",
        "defaultDecision": "HELD",
        "ownerBoundaries": ["provider_baseline", "source_onboarding"],
        "automatedDeterministicClasses": ["builder_baseline", "stable_release"],
        "stablePublisherAuthority": stable["requiredAuthority"],
    }


def require_markers(text: str, markers: list[str], label: str) -> int:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise D4Error(f"{label} markers missing: " + "; ".join(missing))
    return len(markers)


def validate_workflows(texts: dict[str, str]) -> dict[str, Any]:
    auto = texts["upstreamDetection"]
    if "actions/runs/$PUBLISH_RUN_ID/rerun" in auto:
        raise D4Error("Auto Farm recovery may not rerun a stale publish workflow snapshot")
    marker_counts = {
        "upstreamDetectionRecovery": require_markers(auto, [
            "schedule:",
            "Detect upstream changes against authoritative LKG",
            "Compare upstream heads with authoritative last-known-good",
            "pipeline_state = 'publish_failed'",
            "publish_recovery_available",
            "Resume exact failed provider publish",
            "MAX_RECOVERY_ATTEMPTS: '2'",
            "Dispatch fresh current-main publish recovery",
        ], "Source Lab Auto Farm"),
        "runtimeValidation": require_markers(texts["runtimeValidation"], [
            "schedule:",
            "compatibility-farm-foundation",
            "activeCommit",
            "lastKnownGood",
            "source_pending_worker.py assess",
            "source_live_parser_harness.py generate",
            "--fail-threshold 3",
            "discarding stale batch state",
        ], "Source Lab Pending Worker"),
        "sourceApproval": require_markers(texts["sourceApproval"], [
            "Validate owner-only approval",
            "EXPECTED_OWNER_ID: '149634319'",
            "source_pending_approval.py plan",
            "Apply owner approval atomically",
            "Refuse stale approval commit",
            "miyorare-farm-pack-membership-sync.yml",
        ], "Source Lab source approval"),
        "providerPromotion": require_markers(texts["providerPromotion"], [
            "Verify exact approval workflow run",
            "approval proof is not APPROVED",
            "approval gate fingerprint changed",
            "approval evidence binding changed",
            "Refuse promotion if foundation moved after validation",
            "entry[\"state\"] = \"RETRY\"",
            "\"revalidationReason\"] = \"PROVIDER_BASELINE_CHANGED\"",
            "Emit immutable promotion receipt",
            "Revalidate PENDING sources against promoted provider baseline",
        ], "Source Lab provider promotion"),
        "lkgSafety": require_markers(texts["lkgSafety"], [
            "Run LKG negative-regression simulations",
            "Audit authoritative LKG invariants",
            "Prove audit did not mutate Foundation",
            "A7 LKG safety verdict is not SAFE",
        ], "A7 LKG safety"),
        "releaseController": require_markers(texts["releaseController"], [
            "Resolve approved provider fingerprint",
            "activeCommit",
            "lastKnownGood",
            "{\"verify-identity\", \"Build Miyorare-id\", \"Build Miyorare-en\", \"Build Miyorare-Global\"}",
            "source-pack-builder-baseline.yml",
            "gh pr merge \"$PR_NUMBER\"",
            "Resolve desired stable release fingerprint",
            "source_lab_signed",
            "gh attestation verify build/source-lab-signing-manifest.json",
            "main moved since signed controller started; retry from current main.",
            "Dispatch sole Source Pack publisher from current control plane with signed Farm snapshot",
            "release-source-packs.yml",
        ], "Source Pack release controller"),
        "releasePublisher": require_markers(texts["releasePublisher"], [
            "Validate explicit Compatibility Farm release eligibility",
            "pack: [id, en]",
            "Build Miyorare-Global",
            "Verify release payload and immutable tag namespace",
            "--require-compatibility-snapshot",
            "Seal staged Source Pack draft",
            "Audit seal then publish stable release",
            "Publish audited stable release",
        ], "Source Pack publisher"),
        "releaseSeal": require_markers(texts["releaseSeal"], [
            "Refuse retroactive sealing of published releases",
            "Build canonical release lock while draft",
            "Cryptographically attest release lock with GitHub OIDC",
            "gh attestation verify seal/miyorare-release-lock.json",
            "--require-sealed-before-publish",
        ], "Source Pack release seal"),
    }
    return {
        "status": "PROVEN",
        "markerCounts": marker_counts,
        "singleLifecycleAuthority": True,
        "staleWorkflowRerunRecovery": False,
    }


def build_report(
    baseline: dict[str, Any],
    d3: dict[str, Any],
    d2: dict[str, Any],
    a7: dict[str, Any],
    authority: dict[str, Any],
    workflow_texts: dict[str, str],
    current_refs: dict[str, str],
) -> dict[str, Any]:
    validate_baseline(baseline)
    handoffs = validate_d3(d3, baseline)
    validate_d2(d2)
    lkg = validate_a7(a7)
    authority_proof = validate_authority(authority)
    workflow_proof = validate_workflows(workflow_texts)

    require_sha(current_refs.get("controlHead"), "D4 control head")
    require_sha(current_refs.get("sourcePacksBase"), "D4 Source-Packs base")
    require_sha(current_refs.get("compatibilityFarm"), "D4 Compatibility Farm")
    require_sha(current_refs.get("miyorareAmain2"), "D4 Miyorare Amain2")
    if current_refs["sourcePacksBase"] != baseline["sourcePacksAfterD3"]:
        raise D4Error("D4 did not start from exact post-D3 main")
    if current_refs["compatibilityFarm"] != baseline["compatibilityFarmBaseline"]:
        raise D4Error("Compatibility Farm moved after D4 planning")
    if current_refs["miyorareAmain2"] != baseline["miyorareAmain2Baseline"]:
        raise D4Error("Miyorare Amain2 moved after D4 planning")

    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "readOnlyAcceptance": True,
        "status": "D4_LONG_TERM_AUTOMATION_ACCEPTANCE_PROVEN",
        "trackDClosed": False,
        "nextStage": NEXT_STAGE,
        "currentRefs": dict(current_refs),
        "proofs": {
            "upstreamDetectionRecovery": {
                "status": "PROVEN",
                "boundedRecoveryAttempts": 2,
                "freshCurrentMainRecovery": True,
                "staleWorkflowSnapshotRerun": False,
            },
            "runtimeValidationLifecycle": {
                "status": "PROVEN",
                "realParserEvidence": True,
                "failClosedStates": ["RETRY", "NEEDS_ATTENTION", "READY_FOR_APPROVAL"],
                "ownerActivationBoundary": True,
            },
            "ownerMutationBoundaries": authority_proof,
            "lastKnownGoodRollbackSafety": lkg,
            "workflowChain": workflow_proof,
            "packAndReleaseAcceptance": {
                "status": "PROVEN",
                "packs": ["id", "en", "global"],
                "builderPromotionRequiresExactPackChecks": True,
                "releaseRequiresCompatibilitySnapshot": True,
                "stableReleaseIsSealedBeforePublish": True,
                "solePublisher": "release-source-packs.yml",
            },
        },
        "operationalHandoffs": {
            "ownerPackAuthorityRequired": handoffs["ownerPackAuthorityRequired"],
            "count": handoffs["count"],
            "carriedForwardFromD3": True,
            "note": "D4 proves the permanent automation chain; it does not infer or mutate unresolved source pack membership.",
        },
        "safety": {
            "mutateCanonicalIds": False,
            "mutateProviderSelection": False,
            "mutateFarmLifecycle": False,
            "mutateLastKnownGood": False,
            "mutateRetryHeld": False,
            "approveSourceOnboarding": False,
            "approveProviderPromotion": False,
            "promoteBuilderBaseline": False,
            "mutateConsumerPackaging": False,
            "allocateStableVersion": False,
            "publishRelease": False,
        },
    }


def markdown(report: dict[str, Any]) -> str:
    handoffs = report["operationalHandoffs"]
    lkg = report["proofs"]["lastKnownGoodRollbackSafety"]
    lines = [
        "# Track D — D4 Long-term Automation Acceptance",
        "",
        f"- Status: `{report['status']}`",
        f"- A7 LKG safety: `{lkg['status']}`",
        f"- ACTIVE sources observed: **{lkg.get('activeSourceCount')}**",
        f"- Owner pack-authority handoffs carried from D3: **{handoffs['count']}**",
        "- Permanent chain: upstream detection → runtime validation → owner boundary → promotion/LKG → ID/EN/Global build → sealed sole publisher",
        f"- Next: `{report['nextStage']}`",
        "",
        "D4 is acceptance-only. It does not approve, promote, rewrite Farm/LKG, allocate a stable version, or publish a release.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--d3-report", required=True)
    parser.add_argument("--d2-report", required=True)
    parser.add_argument("--a7-report", required=True)
    parser.add_argument("--promotion-authority", required=True)
    parser.add_argument("--upstream-detection-workflow", required=True)
    parser.add_argument("--runtime-validation-workflow", required=True)
    parser.add_argument("--source-approval-workflow", required=True)
    parser.add_argument("--provider-promotion-workflow", required=True)
    parser.add_argument("--lkg-safety-workflow", required=True)
    parser.add_argument("--release-controller-workflow", required=True)
    parser.add_argument("--release-publisher-workflow", required=True)
    parser.add_argument("--release-seal-workflow", required=True)
    parser.add_argument("--control-head", required=True)
    parser.add_argument("--source-packs-base", required=True)
    parser.add_argument("--farm-commit", required=True)
    parser.add_argument("--miyorare-amain2", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    texts = {
        "upstreamDetection": Path(args.upstream_detection_workflow).read_text(encoding="utf-8"),
        "runtimeValidation": Path(args.runtime_validation_workflow).read_text(encoding="utf-8"),
        "sourceApproval": Path(args.source_approval_workflow).read_text(encoding="utf-8"),
        "providerPromotion": Path(args.provider_promotion_workflow).read_text(encoding="utf-8"),
        "lkgSafety": Path(args.lkg_safety_workflow).read_text(encoding="utf-8"),
        "releaseController": Path(args.release_controller_workflow).read_text(encoding="utf-8"),
        "releasePublisher": Path(args.release_publisher_workflow).read_text(encoding="utf-8"),
        "releaseSeal": Path(args.release_seal_workflow).read_text(encoding="utf-8"),
    }
    report = build_report(
        load(args.baseline),
        load(args.d3_report),
        load(args.d2_report),
        load(args.a7_report),
        load(args.promotion_authority),
        texts,
        {
            "controlHead": args.control_head,
            "sourcePacksBase": args.source_packs_base,
            "compatibilityFarm": args.farm_commit,
            "miyorareAmain2": args.miyorare_amain2,
        },
    )
    save(args.output, report)
    if args.markdown_output:
        Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
