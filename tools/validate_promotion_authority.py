#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "governance" / "automation-promotion-authority.v1.json"
WORKFLOWS = ROOT / ".github" / "workflows"
REGISTRY = ROOT / "upstream" / "registry.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    require(policy.get("schemaVersion") == 1, "promotion authority schema must be 1")
    require(policy.get("defaultDecision") == "HELD", "unknown promotion authority must fail closed to HELD")

    classes = policy.get("classes")
    require(isinstance(classes, dict), "promotion authority classes missing")
    require(set(classes) == {"builder_baseline", "provider_baseline", "source_onboarding", "stable_release"}, "unexpected promotion authority class set")

    builder = classes["builder_baseline"]
    require(builder.get("automationMayMerge") is True, "builder baseline is the only automated merge class")
    require(builder.get("ownerApprovalRequired") is False, "builder baseline must remain deterministic automation")
    for gate in ("source-pack-builder-baseline-ci", "main-required-gates", "protected-main-ruleset"):
        require(gate in builder.get("requiredGates", []), f"builder baseline missing gate: {gate}")

    for name in ("provider_baseline", "source_onboarding"):
        item = classes[name]
        require(item.get("automationMayMerge") is False, f"{name} must not be automation-mergeable")
        require(item.get("ownerApprovalRequired") is True, f"{name} must require owner approval")
        require(item.get("failureDecision") == "HELD", f"{name} must fail closed to HELD")

    stable = classes["stable_release"]
    require(stable.get("automationMayMerge") is False, "stable release is publication, not an automated PR merge class")
    require(stable.get("requiredAuthority") == "source-pack-autonomous-release.yml -> release-source-packs.yml", "stable release authority drifted")

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for provider, item in registry.get("providers", {}).items():
        if item.get("autoPromote") is True:
            require(classes["provider_baseline"]["ownerApprovalRequired"] is True, f"{provider} autoPromote metadata must not grant promotion authority")

    approve = (WORKFLOWS / "source-lab-approve-candidate.yml").read_text(encoding="utf-8")
    promote = (WORKFLOWS / "source-lab-promote-candidate.yml").read_text(encoding="utf-8")
    onboarding = (WORKFLOWS / "source-lab-approve-ready-sources.yml").read_text(encoding="utf-8")
    controller = (WORKFLOWS / "source-pack-autonomous-release.yml").read_text(encoding="utf-8")
    publisher = (WORKFLOWS / "release-source-packs.yml").read_text(encoding="utf-8")
    main_gate = (WORKFLOWS / "main-required-gates.yml").read_text(encoding="utf-8")

    owner_marker = "EXPECTED_OWNER_ID: '149634319'"
    owner_check = '[[ "$GITHUB_ACTOR_ID" == "$EXPECTED_OWNER_ID" ]]'
    require(owner_marker in approve and owner_check in approve, "provider approval lost owner binding")
    require(owner_marker in promote and owner_check in promote and "approval_run_id" in promote and "authorized_promotion.py" in promote, "provider promotion lost owner-approved authority chain")
    require(
        owner_marker in onboarding
        and owner_check in onboarding
        and "source_pending_approval.py plan" in onboarding
        and "source_pending_approval.py apply" in onboarding
        and '--approved-by "$GITHUB_ACTOR:$GITHUB_ACTOR_ID"' in onboarding
        and "Refuse stale approval commit" in onboarding,
        "source onboarding lost owner approval authority",
    )

    require('gh pr merge "$PR_NUMBER"' in controller, "builder baseline automated merge path moved; classify it before changing authority")
    require("source-pack-builder-baseline.yml" in controller, "builder baseline exact validation missing")
    require("Main Required Gates" in main_gate and "pull_request:" in main_gate, "protected main gate contract missing")

    require("gh workflow run release-source-packs.yml" in controller, "authoritative controller no longer dispatches sole publisher")
    require(
        "Compute next immutable patch version" in controller
        and "Allocate next immutable stable version" in controller,
        "stable version authority moved from controller",
    )
    require('gh release create "$TAG"' in publisher, "sole publisher no longer owns stable release creation")

    print("P0-C automation promotion authority validated")


if __name__ == "__main__":
    main()
