#!/usr/bin/env python3
"""Track C Batch 4: freeze ID adoption decisions and report future drift.

This phase is observational. It consumes the exact C2 and C3 evidence boundaries,
freezes the ID parity baseline, and hands any authority-changing work back to the
existing Source Lab lifecycle. It never mutates provider selection, Farm authority,
LKG, Retry/Held state, canonical IDs, or Miyorare packaging.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PHASE = "TRACK_C_BATCH_4_ID_ADOPTION_DRIFT"
BASELINE_PHASE = "TRACK_C_BATCH_4_ID_ADOPTION_DRIFT_BASELINE"
C2_PHASE = "TRACK_C_BATCH_2_ID_CAPABILITY_HEALTH_DECISION"
C3_PHASE = "TRACK_C_BATCH_3"
LANGUAGE = "id"
PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

DIRECT_C4_DECISIONS = {
    "NO_C3_REFERENCE_ONLY_PROVIDER_DISCOVERY": "REFERENCE_ONLY_DRIFT_WATCH",
    "NO_C3_REDUNDANT_PROVIDER_DISCOVERY": "REDUNDANT_PROVIDER_DRIFT_WATCH",
    "NO_C3_UMA_NOT_CURATED_REDUNDANT_COVERAGE": "REDUNDANT_UMA_NONCURATION_DRIFT_WATCH",
}
C3_C4_ACTIONS = {
    "C4_REVIEW_STALE_LKG_AND_DEPRECATION": "STALE_LKG_DEPRECATION_REVIEW",
    "C4_RECONCILE_REFERENCE_IDENTITY_WITHOUT_CANONICAL_ID_CHANGE": "REFERENCE_IDENTITY_RECONCILIATION_REVIEW",
    "C4_REVIEW_STALE_ID_FARM_REFERENCE": "STALE_ID_SCOPE_REFERENCE_REVIEW",
    "C4_CONSIDER_SOURCE_SCOPED_ENROLLMENT_THEN_ADOPTION": "PASS_ONLY_ENROLLMENT_ADOPTION_REVIEW",
}


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise ValueError(f"invalid {label} SHA")
    return value


def digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_baseline(baseline: dict[str, Any]) -> None:
    if baseline.get("schemaVersion") != 1 or baseline.get("phase") != BASELINE_PHASE or baseline.get("readOnly") is not True:
        raise ValueError("invalid C4 baseline header")
    refs = baseline.get("refs")
    if not isinstance(refs, dict):
        raise ValueError("C4 baseline refs missing")
    for key in ("sourcePacksAfterBatch3", "sourceInventory", "compatibilityFarm", "miyorareAmain2"):
        require_sha(refs.get(key), key)
    if baseline.get("consumer") != {"repository": "Noirero/Miyorare", "branch": "Amain2"}:
        raise ValueError("C4 consumer must remain Noirero/Miyorare@Amain2")

    artifacts = baseline.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"batch2", "batch3"}:
        raise ValueError("C4 exact artifacts missing")
    for label in ("batch2", "batch3"):
        row = artifacts[label]
        if not isinstance(row, dict):
            raise ValueError(f"invalid {label} artifact metadata")
        if not isinstance(row.get("runId"), int) or not isinstance(row.get("artifactId"), int):
            raise ValueError(f"invalid {label} artifact ids")
        if not isinstance(row.get("name"), str) or not row["name"]:
            raise ValueError(f"invalid {label} artifact name")
        if not isinstance(row.get("digest"), str) or not row["digest"].startswith("sha256:"):
            raise ValueError(f"invalid {label} artifact digest")
        require_sha(row.get("headSha"), f"{label} head")

    c2 = baseline.get("batch2Carry")
    if not isinstance(c2, dict) or c2.get("findingRows") != 9 or c2.get("canonicalSources") != 7:
        raise ValueError("unexpected C2 C4 carry baseline")
    if c2.get("decisions") != {
        "NO_C3_REDUNDANT_PROVIDER_DISCOVERY": 2,
        "NO_C3_REFERENCE_ONLY_PROVIDER_DISCOVERY": 3,
        "NO_C3_UMA_NOT_CURATED_REDUNDANT_COVERAGE": 4,
    }:
        raise ValueError("unexpected C2 C4 decision baseline")
    if len(c2.get("canonicalIds") or []) != 7:
        raise ValueError("unexpected C2 C4 canonical baseline")

    c3 = baseline.get("batch3Boundary")
    if not isinstance(c3, dict):
        raise ValueError("C3 boundary baseline missing")
    if (c3.get("canonicalSources"), c3.get("c2FindingRowsCovered"), c3.get("c4Sources"), c3.get("remediationSources"), c3.get("adoptionEligibleSources")) != (8, 9, 5, 3, 1):
        raise ValueError("unexpected C3 boundary counts")
    if c3.get("decisions") != {
        "CONSUMED_GEKKOUSHI_RUNTIME_NOT_VALIDATED": 1,
        "REFERENCE_MOVED_OUT_OF_ID_SCOPE": 1,
        "REFERENCE_REMOVED_UPSTREAM": 1,
        "REFERENCE_SOURCE_ID_MIGRATION_CONFIRMED": 2,
        "UNCURATED_UMA_RUNTIME_NOT_VALIDATED": 2,
        "UNENROLLED_UMA_RUNTIME_VALIDATED": 1,
    }:
        raise ValueError("unexpected C3 decision baseline")
    if c3.get("adoptionEligibleCanonicalIds") != ["miyorare:inventory-id:THRIVEMOE"]:
        raise ValueError("unexpected C3 adoption candidate")

    if baseline.get("adoptionPolicy") != {
        "mode": "PASS_ONLY",
        "eligibleDecision": "UNENROLLED_UMA_RUNTIME_VALIDATED",
        "requireSourceScopedEnrollment": True,
        "allowImplicitReplacement": False,
        "allowReferenceOnlyPromotion": False,
        "allowAutomaticConsumerMutation": False,
    }:
        raise ValueError("unexpected C4 adoption policy")
    if baseline.get("existingAutomation") != {
        "inventory": ".github/workflows/source-inventory-sync.yml",
        "membership": ".github/workflows/source-lab-sync-farm-membership.yml",
        "runtime": ".github/workflows/source-lab-pending-worker.yml",
        "approval": ".github/workflows/source-lab-approve-ready-sources.yml",
    }:
        raise ValueError("unexpected C4 automation authority")


def validate_c2(report: dict[str, Any], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    if report.get("phase") != C2_PHASE or report.get("readOnly") is not True or report.get("language") != LANGUAGE:
        raise ValueError("invalid exact C2 report")
    summary = report.get("summary")
    if not isinstance(summary, dict) or summary.get("c4FindingRows") != baseline["batch2Carry"]["findingRows"]:
        raise ValueError("C2 C4 finding-row total drifted")
    rows = [
        row for row in report.get("findingDecisions", [])
        if isinstance(row, dict) and isinstance(row.get("decision"), dict) and row["decision"].get("nextPhase") == "TRACK_C_BATCH_4"
    ]
    if len(rows) != baseline["batch2Carry"]["findingRows"]:
        raise ValueError("C2 direct C4 rows incomplete")
    decisions = Counter(str(row["decision"].get("decision")) for row in rows)
    if dict(sorted(decisions.items())) != baseline["batch2Carry"]["decisions"]:
        raise ValueError("C2 direct C4 decisions drifted")
    canonical = sorted({str(row.get("canonicalId")) for row in rows})
    if canonical != baseline["batch2Carry"]["canonicalIds"]:
        raise ValueError("C2 direct C4 canonical cohort drifted")
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("C2 provenance missing")
    refs = baseline["refs"]
    expected = {
        "inventoryCommit": refs["sourceInventory"],
        "foundationCommit": refs["compatibilityFarm"],
        "miyorareCommit": refs["miyorareAmain2"],
        "controlCommit": baseline["artifacts"]["batch2"]["headSha"],
    }
    for key, value in expected.items():
        if provenance.get(key) != value:
            raise ValueError(f"C2 provenance mismatch: {key}")
    return rows


def validate_c3(report: dict[str, Any], baseline: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if report.get("phase") != C3_PHASE or report.get("readOnly") is not True or report.get("language") != LANGUAGE:
        raise ValueError("invalid exact C3 report")
    summary = report.get("summary")
    expected = baseline["batch3Boundary"]
    if not isinstance(summary, dict):
        raise ValueError("C3 summary missing")
    if (summary.get("canonicalSources"), summary.get("c2FindingRowsCovered"), summary.get("remediationRequired")) != (
        expected["canonicalSources"], expected["c2FindingRowsCovered"], expected["remediationSources"]
    ):
        raise ValueError("C3 boundary counts drifted")
    if summary.get("decisions") != expected["decisions"]:
        raise ValueError("C3 decisions drifted")
    rows = report.get("decisions")
    if not isinstance(rows, list) or len(rows) != expected["canonicalSources"]:
        raise ValueError("C3 decision rows incomplete")
    c4_rows = [row for row in rows if isinstance(row, dict) and str(row.get("nextAction") or "").startswith("C4_")]
    remediation = [row for row in rows if isinstance(row, dict) and row.get("nextAction") == "C3_REMEDIATION_REQUIRED"]
    if sorted(str(row.get("canonicalId")) for row in c4_rows) != expected["c4CanonicalIds"]:
        raise ValueError("C3 C4 cohort drifted")
    if sorted(str(row.get("canonicalId")) for row in remediation) != expected["remediationCanonicalIds"]:
        raise ValueError("C3 remediation cohort drifted")
    eligible = [
        str(row.get("canonicalId")) for row in c4_rows
        if row.get("decision") == baseline["adoptionPolicy"]["eligibleDecision"]
    ]
    if eligible != expected["adoptionEligibleCanonicalIds"]:
        raise ValueError("C3 PASS-only adoption cohort drifted")
    for row in c4_rows:
        if row.get("decision") == baseline["adoptionPolicy"]["eligibleDecision"]:
            if row.get("runtimeState") != "CANDIDATE_PASS_LKG_NOT_PASSING_OR_ABSENT":
                raise ValueError("adoption candidate runtime proof drifted")
    safety = report.get("safetyBoundary")
    if not isinstance(safety, dict) or any(bool(value) for value in safety.values()):
        raise ValueError("C3 safety boundary must remain non-mutating")
    return c4_rows, remediation


def provider_identity(provider: str, mapping: dict[str, Any]) -> dict[str, Any]:
    keys = ("module", "sourceId", "sourceName") if provider == "keiyoushi" else ("file", "sourceName")
    return {key: mapping.get(key) for key in keys if mapping.get(key) not in (None, "")}


def inventory_signature(inventory: dict[str, Any]) -> dict[str, Any]:
    if inventory.get("schemaVersion") != 1 or inventory.get("kind") != "MIYORARE_SOURCE_INVENTORY" or inventory.get("informationalOnly") is not True:
        raise ValueError("invalid informational source inventory")
    rows: list[dict[str, Any]] = []
    for source in inventory.get("sources", []):
        if not isinstance(source, dict) or str(source.get("language", "")).lower() != LANGUAGE:
            continue
        providers = source.get("providers")
        if not isinstance(providers, dict) or not providers:
            raise ValueError(f"invalid ID inventory provider map: {source.get('canonicalId')}")
        rows.append({
            "canonicalId": source.get("canonicalId"),
            "providers": {
                provider: provider_identity(provider, providers[provider])
                for provider in PROVIDERS if isinstance(providers.get(provider), dict)
            },
        })
    rows.sort(key=lambda row: str(row["canonicalId"]))
    snapshots = inventory.get("providerSnapshots")
    if not isinstance(snapshots, dict):
        raise ValueError("inventory providerSnapshots missing")
    commits = {}
    for provider in PROVIDERS:
        item = snapshots.get(provider)
        if not isinstance(item, dict):
            raise ValueError(f"inventory snapshot missing for {provider}")
        commits[provider] = require_sha(item.get("commit"), f"inventory {provider}")
    return {"rows": rows, "semanticDigest": digest(rows), "providerCommits": commits, "providerDigest": digest(commits)}


def farm_signature(registry: dict[str, Any]) -> dict[str, Any]:
    if registry.get("schemaVersion") != 1:
        raise ValueError("invalid Compatibility Farm registry")
    rows: list[dict[str, Any]] = []
    for source in registry.get("sources", []):
        if not isinstance(source, dict) or str(source.get("language", "")).lower() != LANGUAGE:
            continue
        providers = source.get("providers")
        identities = source.get("upstreamIdentities")
        if not isinstance(providers, list) or not isinstance(identities, dict):
            raise ValueError(f"invalid ID Farm row: {source.get('canonicalId')}")
        rows.append({
            "canonicalId": source.get("canonicalId"),
            "providers": sorted(str(provider) for provider in providers),
            "upstreamIdentities": {
                provider: provider_identity(provider, identities[provider])
                for provider in PROVIDERS if isinstance(identities.get(provider), dict)
            },
        })
    rows.sort(key=lambda row: str(row["canonicalId"]))
    baselines = registry.get("providerBaselines")
    if not isinstance(baselines, dict):
        raise ValueError("Farm providerBaselines missing")
    provider_baselines = {provider: require_sha(baselines.get(provider), f"Farm {provider}") for provider in PROVIDERS}
    return {"rows": rows, "semanticDigest": digest(rows), "providerBaselines": provider_baselines, "providerDigest": digest(provider_baselines)}


def overlay_signature(root: Path) -> list[dict[str, str]]:
    overlay = root / "extensions/miyorare-sources/overlays/gekkoushi/id"
    if not overlay.is_dir():
        return []
    rows = []
    for path in sorted(item for item in overlay.rglob("*") if item.is_file()):
        rows.append({"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return rows


def consumer_signature(root: Path) -> dict[str, Any]:
    base = root / "extensions/miyorare-sources"
    packs = load_json(base / "packs.json")
    aliases = load_json(base / "multi-upstream.json")
    if packs.get("schema") != 1 or aliases.get("schema") != 1:
        raise ValueError("unsupported Miyorare source manifest schema")
    pack = packs.get("packs", {}).get(LANGUAGE)
    if not isinstance(pack, dict):
        raise ValueError("Miyorare ID pack missing")
    alias_rows: list[dict[str, Any]] = []
    for item in aliases.get("aliases", []):
        if not isinstance(item, dict) or str(item.get("language", "")).lower() != LANGUAGE:
            continue
        official = item.get("official") if isinstance(item.get("official"), dict) else {}
        alias_rows.append({
            "canonicalId": item.get("canonicalId"),
            "verifiedDomain": item.get("verifiedDomain"),
            "official": {key: official.get(key) for key in ("pack", "pluginId", "sourceName") if official.get(key) not in (None, "")},
            "providers": {
                provider: provider_identity(provider, item[provider])
                for provider in PROVIDERS if isinstance(item.get(provider), dict)
            },
        })
    alias_rows.sort(key=lambda row: str(row["canonicalId"]))
    semantic = {
        "sources": sorted(str(value) for value in pack.get("sources", [])),
        "includeAllFrom": sorted(str(value) for value in pack.get("includeAllFrom", [])),
        "aliases": alias_rows,
        "overlays": overlay_signature(root),
    }
    return {"semantic": semantic, "semanticDigest": digest(semantic)}


def changed_ids(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[str]:
    left = {str(row.get("canonicalId")): row for row in before}
    right = {str(row.get("canonicalId")): row for row in after}
    return sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))


def c4_decisions(c2_rows: list[dict[str, Any]], c3_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in c2_rows:
        raw = str(row["decision"]["decision"])
        grouped[str(row["canonicalId"])].append({
            "origin": "C2",
            "action": DIRECT_C4_DECISIONS[raw],
            "finding": row.get("finding"),
            "reason": row["decision"].get("reason"),
        })
    for row in c3_rows:
        next_action = str(row.get("nextAction"))
        grouped[str(row["canonicalId"])].append({
            "origin": "C3",
            "action": C3_C4_ACTIONS[next_action],
            "decision": row.get("decision"),
            "provider": row.get("provider"),
            "runtimeState": row.get("runtimeState"),
        })
    return [{"canonicalId": canonical, "actions": grouped[canonical]} for canonical in sorted(grouped)]


def build_report(
    baseline: dict[str, Any],
    c2: dict[str, Any],
    c3: dict[str, Any],
    inventory_baseline: dict[str, Any],
    inventory_current: dict[str, Any],
    farm_baseline: dict[str, Any],
    farm_current: dict[str, Any],
    miyorare_baseline_root: Path,
    miyorare_current_root: Path,
    current_refs: dict[str, str],
) -> dict[str, Any]:
    validate_baseline(baseline)
    c2_rows = validate_c2(c2, baseline)
    c3_rows, remediation = validate_c3(c3, baseline)
    for key in ("sourceInventory", "compatibilityFarm", "miyorareAmain2"):
        require_sha(current_refs.get(key), f"current {key}")

    inv0, inv1 = inventory_signature(inventory_baseline), inventory_signature(inventory_current)
    farm0, farm1 = farm_signature(farm_baseline), farm_signature(farm_current)
    app0, app1 = consumer_signature(miyorare_baseline_root), consumer_signature(miyorare_current_root)
    flags = {
        "upstreamProviderCommitDrift": inv0["providerCommits"] != inv1["providerCommits"],
        "inventoryIdSemanticDrift": inv0["semanticDigest"] != inv1["semanticDigest"],
        "farmIdSemanticDrift": farm0["semanticDigest"] != farm1["semanticDigest"],
        "farmProviderBaselineDrift": farm0["providerBaselines"] != farm1["providerBaselines"],
        "miyorareAmain2IdSemanticDrift": app0["semanticDigest"] != app1["semanticDigest"],
    }
    drift_required = any(flags.values())
    decisions = c4_decisions(c2_rows, c3_rows)
    action_counts = Counter(action["action"] for row in decisions for action in row["actions"])
    eligible = baseline["batch3Boundary"]["adoptionEligibleCanonicalIds"]
    remediation_ids = sorted(str(row["canonicalId"]) for row in remediation)

    safety = {
        "mutateProviderSelection": False,
        "mutateFarmAuthority": False,
        "mutateLastKnownGood": False,
        "mutateRetryHeld": False,
        "mutateCanonicalId": False,
        "mutateConsumerPackaging": False,
        "autoAdoptProvider": False,
    }
    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "readOnly": True,
        "trackCClosed": False,
        "status": "TRACK_C_C4_COMPLETE_DRIFT_HANDOFF_REQUIRED" if drift_required else "TRACK_C_C4_COMPLETE_WITH_C3_REMEDIATION",
        "baselineRefs": dict(baseline["refs"]),
        "currentRefs": dict(current_refs),
        "batch2": {
            "directC4FindingRows": len(c2_rows),
            "directC4CanonicalSources": len({row["canonicalId"] for row in c2_rows}),
        },
        "batch3": {
            "canonicalSources": c3["summary"]["canonicalSources"],
            "c4Sources": len(c3_rows),
            "remediationSources": len(remediation),
        },
        "c4": {
            "findingRows": len(c2_rows) + len(c3_rows),
            "canonicalSources": len(decisions),
            "decisions": decisions,
            "actions": dict(sorted(action_counts.items())),
        },
        "adoption": {
            "policy": "PASS_ONLY",
            "eligibleRows": len(eligible),
            "canonicalIds": list(eligible),
            "requiresSourceScopedEnrollment": True,
            "providerSelectionChanged": False,
            "adoptionPerformed": False,
            "authority": "EXISTING_SOURCE_LAB_LIFECYCLE",
        },
        "remediation": {
            "phase": "TRACK_C_BATCH_3",
            "remainingRows": len(remediation_ids),
            "canonicalIds": remediation_ids,
        },
        "parity": {
            "inventory": {"baseline": inv0, "current": inv1},
            "farm": {"baseline": farm0, "current": farm1},
            "miyorareAmain2": {"baseline": app0, "current": app1},
        },
        "drift": {
            **flags,
            "inventoryChangedCanonicalIds": changed_ids(inv0["rows"], inv1["rows"]),
            "farmChangedCanonicalIds": changed_ids(farm0["rows"], farm1["rows"]),
        },
        "handoff": {
            "driftRequired": drift_required,
            "identityReconciliation": ["miyorare:inventory-id:IKIRU", "miyorare:inventory-id:MIKOROKU"],
            "deprecationOrScopeReview": ["miyorare:inventory-id:DAILYSUKA", "miyorare:inventory-id:PORNHWA18"],
            "adoptionReview": list(eligible),
            "automation": dict(baseline["existingAutomation"]),
        },
        "safety": safety,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track C Batch 4 — ID Adoption & Drift",
        "",
        f"- Status: `{report['status']}`",
        f"- C4 canonical sources: `{report['c4']['canonicalSources']}`",
        f"- C4 evidence rows: `{report['c4']['findingRows']}`",
        f"- PASS-only adoption candidates: `{report['adoption']['eligibleRows']}`",
        f"- Remaining C3 remediation: `{report['remediation']['remainingRows']}`",
        "- Authority / consumer mutation: `none`",
        "",
        "| Canonical ID | C4 actions |",
        "|---|---|",
    ]
    for row in report["c4"]["decisions"]:
        actions = ", ".join(action["action"] for action in row["actions"])
        lines.append(f"| `{row['canonicalId']}` | `{actions}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--c2-report", required=True)
    parser.add_argument("--c3-report", required=True)
    parser.add_argument("--inventory-baseline", required=True)
    parser.add_argument("--inventory-current", required=True)
    parser.add_argument("--farm-baseline", required=True)
    parser.add_argument("--farm-current", required=True)
    parser.add_argument("--miyorare-baseline-root", required=True)
    parser.add_argument("--miyorare-current-root", required=True)
    parser.add_argument("--inventory-current-commit", required=True)
    parser.add_argument("--farm-current-commit", required=True)
    parser.add_argument("--miyorare-current-commit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    report = build_report(
        load_json(args.baseline),
        load_json(args.c2_report),
        load_json(args.c3_report),
        load_json(args.inventory_baseline),
        load_json(args.inventory_current),
        load_json(args.farm_baseline),
        load_json(args.farm_current),
        Path(args.miyorare_baseline_root),
        Path(args.miyorare_current_root),
        {
            "sourceInventory": args.inventory_current_commit,
            "compatibilityFarm": args.farm_current_commit,
            "miyorareAmain2": args.miyorare_current_commit,
        },
    )
    save_json(args.output, report)
    Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
