#!/usr/bin/env python3
"""Track D D5 closure and transitional-workflow cleanup audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PHASE = "TRACK_D_D5_CLOSURE_TRANSITIONAL_CLEANUP"
D4_PHASE = "TRACK_D_D4_LONG_TERM_AUTOMATION_ACCEPTANCE"
D4_STATUS = "D4_LONG_TERM_AUTOMATION_ACCEPTANCE_PROVEN"
STATUS_CLEAN = "TRACK_D_CLOSED"
STATUS_HANDOFFS = "TRACK_D_CLOSED_WITH_OPERATIONAL_HANDOFFS"


class ClosureError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ClosureError(f"{path}: expected JSON object")
    return data


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ClosureError(message)


def build_report(
    baseline: dict[str, Any],
    d4_report: dict[str, Any],
    repo_root: Path,
    *,
    control_head: str,
    source_packs_base: str,
    farm_commit: str,
    miyorare_amain2: str,
) -> dict[str, Any]:
    require(baseline.get("schemaVersion") == 1, "unsupported D5 baseline schema")
    require(baseline.get("phase") == PHASE, "invalid D5 phase")
    require(baseline.get("sourcePacksAfterD4") == source_packs_base, "D5 base is not exact post-D4 main")

    artifact = baseline.get("d4Artifact")
    require(isinstance(artifact, dict), "missing D4 artifact binding")
    require(artifact.get("requiredStatus") == D4_STATUS, "invalid D4 status binding")

    require(d4_report.get("phase") == D4_PHASE, "invalid D4 report phase")
    require(d4_report.get("status") == D4_STATUS, "D4 acceptance is not proven")
    require(d4_report.get("trackDClosed") is False, "D4 report unexpectedly closed Track D")
    require(d4_report.get("nextStage") == PHASE, "D4 does not hand off to D5")
    proofs = d4_report.get("proofs")
    require(isinstance(proofs, dict) and proofs, "missing D4 proof set")
    require(all(isinstance(v, dict) and v.get("status") == "PROVEN" for v in proofs.values()), "not every D4 proof is PROVEN")
    safety = d4_report.get("safety")
    require(isinstance(safety, dict) and not any(bool(v) for v in safety.values()), "D4 safety boundary was violated")

    permanent = baseline.get("permanentMaintenanceWorkflows")
    require(isinstance(permanent, list) and permanent, "missing permanent workflow classification")
    missing_permanent = [path for path in permanent if not (repo_root / path).is_file()]
    require(not missing_permanent, f"missing permanent workflow(s): {missing_permanent}")

    scheduled = baseline.get("scheduledCoverage")
    require(isinstance(scheduled, dict) and scheduled, "missing scheduled maintenance coverage")
    for label, path in scheduled.items():
        workflow = repo_root / str(path)
        require(workflow.is_file(), f"scheduled {label} workflow is missing: {path}")
        text = workflow.read_text(encoding="utf-8")
        require("schedule:" in text, f"scheduled {label} coverage lost its schedule trigger: {path}")

    retired = baseline.get("retiredTransitionalWorkflows")
    require(isinstance(retired, list) and retired, "missing transitional retirement classification")
    still_active = [path for path in retired if (repo_root / path).exists()]
    require(not still_active, f"transitional workflow(s) still active: {still_active}")

    frozen = baseline.get("frozenEvidence")
    require(isinstance(frozen, list) and frozen, "missing frozen evidence list")
    missing_evidence = [path for path in frozen if not (repo_root / path).is_file()]
    require(not missing_evidence, f"frozen evidence missing: {missing_evidence}")

    historical = baseline.get("historicalImplementations")
    require(isinstance(historical, list) and historical, "missing historical implementation list")
    missing_history = [path for path in historical if not (repo_root / path).is_file()]
    require(not missing_history, f"historical implementation missing: {missing_history}")

    handoffs = d4_report.get("operationalHandoffs")
    require(isinstance(handoffs, dict), "missing D4 operational handoffs")
    require(handoffs.get("carriedForwardFromD3") is True, "D4 did not preserve D3 operational handoffs")
    handoff_ids = handoffs.get("ownerPackAuthorityRequired")
    require(isinstance(handoff_ids, list), "invalid owner pack-authority handoff list")
    require(handoffs.get("count") == len(handoff_ids), "D4 handoff count/list mismatch")

    semantics = baseline.get("closureSemantics")
    require(isinstance(semantics, dict), "missing closure semantics")
    require(semantics.get("unresolvedOperationalHandoffsMayRemain") is True, "D5 closure must preserve unresolved operational handoffs")

    status = STATUS_HANDOFFS if handoff_ids else STATUS_CLEAN
    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "status": status,
        "trackDClosed": True,
        "nextStage": None,
        "currentRefs": {
            "controlHead": control_head,
            "sourcePacksBase": source_packs_base,
            "compatibilityFarm": farm_commit,
            "miyorareAmain2": miyorare_amain2,
        },
        "closure": {
            "permanentMaintenanceModelEstablished": True,
            "transitionalWorkflowsRetired": True,
            "historicalEvidencePreserved": True,
            "permanentWorkflowCount": len(permanent),
            "retiredWorkflowCount": len(retired),
            "frozenEvidenceCount": len(frozen),
            "historicalImplementationCount": len(historical),
        },
        "permanentMaintenanceWorkflows": permanent,
        "retiredTransitionalWorkflows": retired,
        "operationalHandoffs": {
            "count": len(handoff_ids),
            "ownerPackAuthorityRequired": handoff_ids,
            "carriedForwardFromD3": True,
            "blocksTrackClosure": False,
        },
        "closureSemantics": semantics,
        "safety": {
            "mutateCanonicalIds": False,
            "mutateFarmLifecycle": False,
            "mutateLastKnownGood": False,
            "mutateProviderSelection": False,
            "mutateRetryHeld": False,
            "approveSourceOnboarding": False,
            "approveProviderPromotion": False,
            "mutateConsumerPackaging": False,
            "promoteBuilderBaseline": False,
            "allocateStableVersion": False,
            "publishRelease": False,
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    handoffs = report["operationalHandoffs"]
    closure = report["closure"]
    lines = [
        "# Track D — D5 Closure / Transitional Cleanup",
        "",
        f"- Status: `{report['status']}`",
        f"- Track D closed: `{str(report['trackDClosed']).lower()}`",
        f"- Permanent workflows: **{closure['permanentWorkflowCount']}**",
        f"- Retired transitional workflows: **{closure['retiredWorkflowCount']}**",
        f"- Preserved frozen evidence files: **{closure['frozenEvidenceCount']}**",
        f"- Operational handoffs carried forward: **{handoffs['count']}**",
        "",
        "Track closure means the permanent maintenance model is established. It does not claim every source is healthy or every operational handoff is resolved.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--d4-report", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--control-head", required=True)
    parser.add_argument("--source-packs-base", required=True)
    parser.add_argument("--farm-commit", required=True)
    parser.add_argument("--miyorare-amain2", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(
        load_json(args.baseline),
        load_json(args.d4_report),
        args.repo_root,
        control_head=args.control_head,
        source_packs_base=args.source_packs_base,
        farm_commit=args.farm_commit,
        miyorare_amain2=args.miyorare_amain2,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report, args.markdown_output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
