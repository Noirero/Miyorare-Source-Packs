#!/usr/bin/env python3
"""Track B Batch 4: freeze EN parity, enforce PASS-only adoption, and report drift.

This layer is observational. Existing Source Lab inventory/Farm/PENDING/approval/promotion
workflows remain lifecycle authority. It never mutates provider selection, Compatibility Farm
state, LKG, Retry/Held, canonical IDs, or overlays.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

PHASE = "TRACK_B_BATCH_4_ADOPTION_DRIFT"
BASELINE_PHASE = "TRACK_B_BATCH_4_ADOPTION_DRIFT_BASELINE"
B3_PHASE = "TRACK_B_BATCH_3_IDENTITY_CLOSURE"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_B3_ROUTES = {
    "LIVE_ACCESS_BLOCKED": 8,
    "LIVE_DOMAIN_DISPOSITION": 1,
    "PROVEN_UPSTREAM_DEAD": 23,
    "PROVEN_UPSTREAM_MIGRATION": 1,
}
PASS_ADOPTION_ROUTE = "B4_CANDIDATE_RUNTIME_PROVEN"
PROVIDERS = ("keiyoushi", "uma", "gekkoushi")


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


def validate_baseline(baseline: dict[str, Any]) -> None:
    if (
        baseline.get("schemaVersion") != 1
        or baseline.get("phase") != BASELINE_PHASE
        or baseline.get("readOnly") is not True
    ):
        raise ValueError("invalid B4 baseline header")
    refs = baseline.get("refs")
    if not isinstance(refs, dict):
        raise ValueError("B4 baseline refs missing")
    for key in ("sourcePacksAfterBatch3", "sourceInventory", "compatibilityFarm", "miyorareAmain2"):
        require_sha(refs.get(key), key)
    if baseline.get("consumer") != {"repository": "Noirero/Miyorare", "branch": "Amain2"}:
        raise ValueError("B4 consumer must be Noirero/Miyorare@Amain2")
    closure = baseline.get("batch3Closure")
    if not isinstance(closure, dict):
        raise ValueError("B3 closure baseline missing")
    if closure.get("rows") != 33 or closure.get("evidenceBackedRows") != 33:
        raise ValueError("B3 closure baseline must cover all 33 rows")
    if closure.get("routes") != EXPECTED_B3_ROUTES:
        raise ValueError("unexpected B3 route baseline")
    if closure.get("adoptionEligibleRows") != 0:
        raise ValueError("B4 baseline must not pre-authorize adoption")
    if baseline.get("adoptionPolicy") != {
        "mode": "PASS_ONLY",
        "eligibleRoute": PASS_ADOPTION_ROUTE,
        "allowImplicitReplacement": False,
        "allowReferenceOnlyPromotion": False,
    }:
        raise ValueError("unexpected B4 adoption policy")
    required_automation = {
        "inventory": ".github/workflows/source-inventory-sync.yml",
        "membership": ".github/workflows/source-lab-sync-farm-membership.yml",
        "runtime": ".github/workflows/source-lab-pending-worker.yml",
        "approval": ".github/workflows/source-lab-approve-ready-sources.yml",
    }
    if baseline.get("existingAutomation") != required_automation:
        raise ValueError("B4 must hand off to existing Source Lab automation")


def validate_b3_closure(report: dict[str, Any], baseline: dict[str, Any]) -> None:
    if (
        report.get("schemaVersion") != 1
        or report.get("phase") != B3_PHASE
        or report.get("readOnly") is not True
    ):
        raise ValueError("invalid final B3 closure")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("B3 summary missing")
    if summary.get("rows") != 33 or summary.get("evidenceBackedRows") != 33:
        raise ValueError("B3 closure is not 33/33 evidence-backed")
    if summary.get("routes") != baseline["batch3Closure"]["routes"]:
        raise ValueError("B3 route totals drifted from frozen B4 baseline")
    decisions = report.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != 33:
        raise ValueError("B3 decisions must contain 33 rows")
    safety = report.get("safety")
    if not isinstance(safety, dict) or any(bool(value) for value in safety.values()):
        raise ValueError("B3 closure safety must remain non-mutating")


def provider_identity(provider: str, mapping: dict[str, Any]) -> dict[str, Any]:
    keys = ("module", "sourceId", "sourceName") if provider == "keiyoushi" else ("file", "sourceName")
    return {key: mapping.get(key) for key in keys if mapping.get(key) not in (None, "")}


def digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def inventory_signature(inventory: dict[str, Any]) -> dict[str, Any]:
    if (
        inventory.get("schemaVersion") != 1
        or inventory.get("kind") != "MIYORARE_SOURCE_INVENTORY"
        or inventory.get("informationalOnly") is not True
    ):
        raise ValueError("invalid informational source inventory")
    rows: list[dict[str, Any]] = []
    for source in inventory.get("sources", []):
        if not isinstance(source, dict) or str(source.get("language", "")).lower() != "en":
            continue
        providers = source.get("providers")
        if not isinstance(providers, dict) or not providers:
            raise ValueError(f"invalid EN inventory provider map: {source.get('canonicalId')}")
        rows.append({
            "canonicalId": source.get("canonicalId"),
            "providers": {
                provider: provider_identity(provider, providers[provider])
                for provider in PROVIDERS
                if isinstance(providers.get(provider), dict)
            },
        })
    rows.sort(key=lambda row: str(row["canonicalId"]))
    snapshots = inventory.get("providerSnapshots")
    if not isinstance(snapshots, dict):
        raise ValueError("inventory providerSnapshots missing")
    commits: dict[str, str] = {}
    for provider in PROVIDERS:
        item = snapshots.get(provider)
        if not isinstance(item, dict):
            raise ValueError(f"inventory snapshot missing for {provider}")
        commits[provider] = require_sha(item.get("commit"), f"inventory {provider}")
    return {
        "rows": rows,
        "semanticDigest": digest(rows),
        "providerCommits": commits,
        "providerDigest": digest(commits),
    }


def farm_signature(registry: dict[str, Any]) -> dict[str, Any]:
    if registry.get("schemaVersion") != 1:
        raise ValueError("invalid Compatibility Farm registry")
    rows: list[dict[str, Any]] = []
    for source in registry.get("sources", []):
        if not isinstance(source, dict) or str(source.get("language", "")).lower() != "en":
            continue
        providers = source.get("providers")
        identities = source.get("upstreamIdentities")
        if not isinstance(providers, list) or not isinstance(identities, dict):
            raise ValueError(f"invalid EN Farm row: {source.get('canonicalId')}")
        rows.append({
            "canonicalId": source.get("canonicalId"),
            "providers": sorted(str(provider) for provider in providers),
            "upstreamIdentities": {
                provider: provider_identity(provider, identities[provider])
                for provider in PROVIDERS
                if isinstance(identities.get(provider), dict)
            },
        })
    rows.sort(key=lambda row: str(row["canonicalId"]))
    baselines = registry.get("providerBaselines")
    if not isinstance(baselines, dict):
        raise ValueError("Farm providerBaselines missing")
    provider_baselines = {
        provider: require_sha(baselines.get(provider), f"Farm {provider}")
        for provider in PROVIDERS
    }
    return {
        "rows": rows,
        "semanticDigest": digest(rows),
        "providerBaselines": provider_baselines,
        "providerDigest": digest(provider_baselines),
    }


def overlay_signature(root: Path) -> list[dict[str, str]]:
    overlay = root / "extensions/miyorare-sources/overlays/gekkoushi/en"
    if not overlay.is_dir():
        return []
    rows = []
    for path in sorted(item for item in overlay.rglob("*") if item.is_file()):
        rows.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return rows


def consumer_signature(root: Path) -> dict[str, Any]:
    base = root / "extensions/miyorare-sources"
    packs = load_json(base / "packs.json")
    aliases = load_json(base / "multi-upstream.json")
    if packs.get("schema") != 1 or aliases.get("schema") != 1:
        raise ValueError("unsupported Miyorare source manifest schema")
    en_pack = packs.get("packs", {}).get("en")
    if not isinstance(en_pack, dict):
        raise ValueError("Miyorare EN pack missing")
    alias_rows: list[dict[str, Any]] = []
    for item in aliases.get("aliases", []):
        if not isinstance(item, dict) or str(item.get("language", "")).lower() != "en":
            continue
        official = item.get("official") if isinstance(item.get("official"), dict) else {}
        alias_rows.append({
            "canonicalId": item.get("canonicalId"),
            "verifiedDomain": item.get("verifiedDomain"),
            "official": {
                key: official.get(key)
                for key in ("pack", "pluginId", "sourceName")
                if official.get(key) not in (None, "")
            },
            "providers": {
                provider: provider_identity(provider, item[provider])
                for provider in PROVIDERS
                if isinstance(item.get(provider), dict)
            },
        })
    alias_rows.sort(key=lambda row: str(row["canonicalId"]))
    semantic = {
        # Provider commit pins are intentionally excluded: Source-Packs materialization owns
        # provider commit authority. This signature protects consumer membership/identity/overlays.
        "sources": sorted(str(value) for value in en_pack.get("sources", [])),
        "includeAllFrom": sorted(str(value) for value in en_pack.get("includeAllFrom", [])),
        "aliases": alias_rows,
        "overlays": overlay_signature(root),
    }
    return {"semantic": semantic, "semanticDigest": digest(semantic)}


def changed_ids(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[str]:
    left = {str(row.get("canonicalId")): row for row in before}
    right = {str(row.get("canonicalId")): row for row in after}
    return sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))


def build_report(
    baseline: dict[str, Any],
    b3_closure: dict[str, Any],
    inventory_baseline: dict[str, Any],
    inventory_current: dict[str, Any],
    farm_baseline: dict[str, Any],
    farm_current: dict[str, Any],
    miyorare_baseline_root: Path,
    miyorare_current_root: Path,
    current_refs: dict[str, str],
) -> dict[str, Any]:
    validate_baseline(baseline)
    validate_b3_closure(b3_closure, baseline)
    for key in ("sourceInventory", "compatibilityFarm", "miyorareAmain2"):
        require_sha(current_refs.get(key), f"current {key}")

    inv0, inv1 = inventory_signature(inventory_baseline), inventory_signature(inventory_current)
    farm0, farm1 = farm_signature(farm_baseline), farm_signature(farm_current)
    app0, app1 = consumer_signature(miyorare_baseline_root), consumer_signature(miyorare_current_root)

    eligible = [
        row["canonicalId"]
        for row in b3_closure["decisions"]
        if row.get("route") == PASS_ADOPTION_ROUTE
    ]
    if eligible:
        raise ValueError("B3 closure unexpectedly contains adoption candidates without isolated B4 proof")

    flags = {
        "upstreamProviderCommitDrift": inv0["providerCommits"] != inv1["providerCommits"],
        "inventoryEnSemanticDrift": inv0["semanticDigest"] != inv1["semanticDigest"],
        "farmEnSemanticDrift": farm0["semanticDigest"] != farm1["semanticDigest"],
        "farmProviderBaselineDrift": farm0["providerBaselines"] != farm1["providerBaselines"],
        "miyorareAmain2EnSemanticDrift": app0["semanticDigest"] != app1["semanticDigest"],
    }
    needs_source_lab = any(flags.values())
    drift = {
        **flags,
        "inventoryChangedCanonicalIds": changed_ids(inv0["rows"], inv1["rows"]),
        "farmChangedCanonicalIds": changed_ids(farm0["rows"], farm1["rows"]),
    }

    return {
        "schemaVersion": 1,
        "phase": PHASE,
        "readOnly": True,
        "trackBClosed": True,
        "status": "TRACK_B_CLOSED_DRIFT_HANDOFF_REQUIRED" if needs_source_lab else "TRACK_B_CLOSED_BASELINE_CLEAN",
        "baselineRefs": dict(baseline["refs"]),
        "currentRefs": dict(current_refs),
        "batch3": {
            "rows": 33,
            "evidenceBackedRows": 33,
            "routes": dict(b3_closure["summary"]["routes"]),
        },
        "adoption": {
            "policy": "PASS_ONLY",
            "eligibleRows": len(eligible),
            "canonicalIds": eligible,
            "providerSelectionChanged": False,
            "adoptionPerformed": False,
            "reason": "NO_RUNTIME_PASS_ELIGIBLE_ROWS",
        },
        "parity": {
            "inventory": {"baseline": inv0, "current": inv1},
            "farm": {"baseline": farm0, "current": farm1},
            "miyorareAmain2": {"baseline": app0, "current": app1},
        },
        "drift": drift,
        "handoff": {
            "required": needs_source_lab,
            "mode": "EXISTING_SOURCE_LAB_PIPELINE" if needs_source_lab else "NO_HANDOFF_REQUIRED",
            "automation": dict(baseline["existingAutomation"]),
            "note": "Inventory/Farm/PENDING/approval/promotion automation remains authoritative; this report does not dispatch or promote.",
        },
        "safety": {
            "mutatesAuthority": False,
            "mutatesCanonicalIds": False,
            "mutatesLastKnownGood": False,
            "mutatesRetryHeld": False,
            "promotesProvider": False,
            "approvesOverlay": False,
            "dispatchesPromotion": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track B Batch 4 — EN adoption & drift closure",
        "",
        f"Status: **{report['status']}**",
        "",
        "## Adoption",
        "",
        f"- policy: `{report['adoption']['policy']}`",
        f"- eligible rows: {report['adoption']['eligibleRows']}",
        f"- adoption performed: {str(report['adoption']['adoptionPerformed']).lower()}",
        "",
        "## Final Batch 3 routes",
        "",
    ]
    for name, count in sorted(report["batch3"]["routes"].items()):
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Drift", ""])
    for key in (
        "upstreamProviderCommitDrift",
        "inventoryEnSemanticDrift",
        "farmEnSemanticDrift",
        "farmProviderBaselineDrift",
        "miyorareAmain2EnSemanticDrift",
    ):
        lines.append(f"- `{key}`: {str(report['drift'][key]).lower()}")
    lines.extend([
        "",
        "## Handoff",
        "",
        f"- required: {str(report['handoff']['required']).lower()}",
        f"- mode: `{report['handoff']['mode']}`",
        "",
        "Track B is closed. Future EN drift must flow through the existing inventory → Farm PENDING → runtime validation → owner approval/promotion pipeline.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--b3-closure", required=True)
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
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    report = build_report(
        load_json(args.baseline),
        load_json(args.b3_closure),
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
    if args.markdown_output:
        target = Path(args.markdown_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
