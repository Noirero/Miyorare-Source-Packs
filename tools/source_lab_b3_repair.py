#!/usr/bin/env python3
"""Track B Batch 3 targeted repair experiment and terminal decision builder.

Repairs are applied only to disposable provider checkouts. This module never
writes Compatibility Farm authority, LKG, Retry/Held state, or canonical IDs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PRIMARY = ("uma", "gekkoushi")
TARGETS: dict[tuple[str, str], dict[str, Any]] = {
    ("miyorare:inventory-en:PAWMANGA", "gekkoushi"): {
        "file": "src/main/kotlin/tsuki/site/madara/en/PawManga.kt",
        "replacements": [(
            'MadaraParser(context, MangaParserSource.PAWMANGA, "pawmanga.com", 10)\n',
            'MadaraParser(context, MangaParserSource.PAWMANGA, "pawmanga.com", 10) {\n'
            '\toverride val withoutAjax = true\n'
            '\toverride val tagPrefix = "genre/"\n'
            '\toverride val listUrl = "webtoon/"\n'
            '}\n',
        )],
        "reference": "Nyora current Madara profile: withoutAjax + genre/ + webtoon/",
    },
    ("miyorare:inventory-en:WHALEMANGA", "gekkoushi"): {
        "file": "src/main/kotlin/tsuki/site/madara/en/WhaleManga.kt",
        "replacements": [(
            'MadaraParser(context, MangaParserSource.WHALEMANGA, "whalemanga.com", 10)\n',
            'MadaraParser(context, MangaParserSource.WHALEMANGA, "whalemanga.com", 10) {\n'
            '\toverride val withoutAjax = true\n'
            '\toverride val tagPrefix = "webtoon-genre/"\n'
            '\toverride val listUrl = "read/"\n'
            '}\n',
        )],
        "reference": "Nyora current Madara profile: withoutAjax + webtoon-genre/ + read/",
    },
    ("miyorare:inventory-en:NOVELCROW", "gekkoushi"): {
        "file": "src/main/kotlin/tsuki/site/madara/en/Novelcrow.kt",
        "replacements": [(
            '\toverride val tagPrefix = "comic-genre/"\n',
            '\toverride val withoutAjax = true\n'
            '\toverride val tagPrefix = "genre/"\n'
            '\toverride val listUrl = "webtoon/"\n',
        )],
        "reference": "Nyora current Madara profile: withoutAjax + genre/ + webtoon/",
    },
    ("miyorare:inventory-en:NOVELCROW", "uma"): {
        "file": "src/main/kotlin/tsuki/site/en/nsfw/NovelCrow.kt",
        "replacements": [
            ('    override val tagPrefix = "genres-2/"\n', '    override val tagPrefix = "genre/"\n'),
            ('    override val listUrl = ""\n', '    override val listUrl = "webtoon/"\n'),
        ],
        "reference": "Nyora current Madara profile: genre/ + webtoon/ (UMA already withoutAjax)",
    },
}


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def apply_profile(root: Path, canonical_id: str, provider: str) -> dict[str, Any]:
    spec = TARGETS.get((canonical_id, provider))
    if spec is None:
        raise ValueError(f"no B3 repair profile for {canonical_id}/{provider}")
    path = root / spec["file"]
    if not path.is_file():
        raise ValueError(f"repair target missing: {path}")
    original = path.read_text(encoding="utf-8")
    text = original
    changes = []
    for old, new in spec["replacements"]:
        count = text.count(old)
        if count != 1:
            raise ValueError(f"{canonical_id}/{provider}: expected one baseline occurrence, found {count}")
        text = text.replace(old, new, 1)
        changes.append({"old": old.rstrip(), "new": new.rstrip()})
    if text == original:
        raise ValueError(f"{canonical_id}/{provider}: repair produced no change")
    path.write_text(text, encoding="utf-8")
    return {
        "canonicalId": canonical_id,
        "provider": provider,
        "file": spec["file"],
        "reference": spec["reference"],
        "beforeSha256": hashlib.sha256(original.encode()).hexdigest(),
        "afterSha256": hashlib.sha256(text.encode()).hexdigest(),
        "changes": changes,
    }


def build_repair_plan(base_plan: dict[str, Any]) -> dict[str, Any]:
    by_id = {row["canonicalId"]: row for row in base_plan.get("items", []) if isinstance(row, dict)}
    items = []
    for canonical_id in sorted({cid for cid, _ in TARGETS}):
        source = by_id.get(canonical_id)
        if source is None:
            raise ValueError(f"repair target absent from B3 cohort: {canonical_id}")
        providers = sorted(provider for cid, provider in TARGETS if cid == canonical_id)
        identities = {}
        for provider in providers:
            binding = source.get("candidate", {}).get(provider, {})
            identity = binding.get("identity") if isinstance(binding, dict) else None
            if not isinstance(identity, dict) or not identity.get("file"):
                raise ValueError(f"repair target is not candidate-bound: {canonical_id}/{provider}")
            identities[provider] = identity
        items.append({
            "canonicalId": canonical_id,
            "providers": providers,
            "upstreamIdentities": identities,
            "attempts": 0,
            "previousAttempts": 0,
            "lifetimeAttempts": 0,
            "baselineReset": False,
        })
    return {"schemaVersion": 2, "side": "repaired-candidate", "count": len(items), "items": items}


def result_map(data: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out = {}
    for row in data.get("results", []):
        if isinstance(row, dict) and isinstance(row.get("canonicalId"), str) and row.get("provider") in PRIMARY:
            out[(row["canonicalId"], row["provider"])] = row
    return out


def profile_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["canonicalId"]: row
        for row in data.get("results", [])
        if isinstance(row, dict) and isinstance(row.get("canonicalId"), str)
    }


def runtime_pass(row: dict[str, Any] | None) -> bool:
    return bool(
        row
        and row.get("status") == "PASS"
        and row.get("parserExecution") is True
        and row.get("detailsTraversal") is True
        and row.get("chapterTraversal") is True
        and row.get("pageExtraction") is True
    )


def finalize(
    plan: dict[str, Any],
    candidate_profile: dict[str, Any],
    lkg_profile: dict[str, Any],
    candidate_live: dict[str, Any],
    lkg_live: dict[str, Any],
    repaired_live: dict[str, Any],
    repair_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    cp = profile_map(candidate_profile)
    lp = profile_map(lkg_profile)
    cr = result_map(candidate_live)
    lr = result_map(lkg_live)
    rr = result_map(repaired_live)
    receipt_map = {(r["canonicalId"], r["provider"]): r for r in repair_receipts}
    decisions = []
    counts: dict[str, int] = {}

    for item in plan.get("items", []):
        cid = item["canonicalId"]
        bound = []
        for provider in PRIMARY:
            cb = item.get("candidate", {}).get(provider, {})
            lb = item.get("lkg", {}).get(provider, {})
            if isinstance(cb.get("identity"), dict) or isinstance(lb.get("identity"), dict):
                bound.append(provider)

        repaired_pass = sorted(
            provider for provider in PRIMARY
            if (cid, provider) in receipt_map and runtime_pass(rr.get((cid, provider)))
        )
        baseline_pass = sorted(
            provider for provider in PRIMARY
            if runtime_pass(cr.get((cid, provider))) or runtime_pass(lr.get((cid, provider)))
        )
        categories = {
            row.get("failureCategory")
            for row in (cp.get(cid), lp.get(cid))
            if isinstance(row, dict) and row.get("failureCategory")
        }

        if repaired_pass:
            decision = "B4_REPAIR_RUNTIME_PROVEN"
            next_phase = "TRACK_B_BATCH_4"
            reason = "A disposable targeted repair converted a failing primary baseline into a full real-parser PASS."
        elif baseline_pass:
            decision = "B4_PRIMARY_RUNTIME_PROVEN"
            next_phase = "TRACK_B_BATCH_4"
            reason = "A primary candidate or LKG already has full real-parser PASS evidence."
        elif not bound:
            decision = "B3_UNSUPPORTED_NO_PRIMARY_IMPLEMENTATION"
            next_phase = "TRACK_D"
            reason = "Neither UMA nor Gekkoushi contains a bound implementation at the frozen B3 boundary."
        elif categories and categories <= {"NETWORK_TRANSIENT", "PROFILE_TRANSIENT"}:
            decision = "B3_TEMPORARILY_UNAVAILABLE_NETWORK"
            next_phase = "TRACK_D"
            reason = "Primary implementations exist, but candidate and LKG could not reach the configured source host during B3."
        elif any(cid == target for target, _ in TARGETS):
            decision = "B3_UNSUPPORTED_AFTER_TARGETED_REPAIR"
            next_phase = "TRACK_D"
            reason = "Primary baseline failed and the evidence-backed targeted repair did not achieve full real-parser PASS."
        else:
            decision = "B3_UNSUPPORTED_SOURCE_REWRITE_REQUIRED"
            next_phase = "TRACK_D"
            reason = "The site is reachable but candidate and LKG both fail live parsing; no safe bounded repair profile is proven."

        counts[decision] = counts.get(decision, 0) + 1
        decisions.append({
            "canonicalId": cid,
            "displayName": item.get("displayName"),
            "decision": decision,
            "nextPhase": next_phase,
            "reason": reason,
            "boundPrimaryProviders": sorted(bound),
            "baselineRuntimePassProviders": baseline_pass,
            "repairRuntimePassProviders": repaired_pass,
            "profileFailureCategories": sorted(categories),
            "repairReceipts": [receipt_map[(cid, p)] for p in PRIMARY if (cid, p) in receipt_map],
            "safety": {
                "readOnlyAuthority": True,
                "mutateLastKnownGood": False,
                "mutateRetryHeld": False,
                "mutateCanonicalId": False,
                "promoteProvider": False,
                "adoptReferenceProvider": False,
            },
        })

    if len(decisions) != plan.get("count"):
        raise ValueError("final B3 decision count does not match plan")
    return {
        "schemaVersion": 1,
        "phase": "TRACK_B_BATCH_3",
        "status": "COMPLETE_WITH_TERMINAL_DECISIONS",
        "readOnlyAuthority": True,
        "cohortSha256": plan.get("cohortSha256"),
        "summary": {"rows": len(decisions), "decisions": counts},
        "decisions": decisions,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Track B Batch 3 — Targeted Repair & Runtime Decision",
        "",
        f"Status: **{report['status']}**",
        "",
        "Compatibility Farm authority remained read-only; repairs were tested only in disposable upstream checkouts.",
        "",
        f"Rows: **{report['summary']['rows']}**",
        "",
        "## Decision counts",
    ]
    for key, value in sorted(report["summary"]["decisions"].items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Sources", ""]
    for row in report["decisions"]:
        repair = ",".join(row["repairRuntimePassProviders"]) or "-"
        lines.append(f"- `{row['canonicalId']}` — **{row['decision']}** → `{row['nextPhase']}`; repair PASS: `{repair}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("apply")
    a.add_argument("--provider-root", required=True)
    a.add_argument("--provider", required=True, choices=PRIMARY)
    a.add_argument("--canonical-id", required=True)
    a.add_argument("--receipt", required=True)
    rp = sub.add_parser("plan")
    rp.add_argument("--b3-plan", required=True)
    rp.add_argument("--output", required=True)
    f = sub.add_parser("finalize")
    f.add_argument("--b3-plan", required=True)
    f.add_argument("--candidate-profile", required=True)
    f.add_argument("--lkg-profile", required=True)
    f.add_argument("--candidate-live", required=True)
    f.add_argument("--lkg-live", required=True)
    f.add_argument("--repaired-live", required=True)
    f.add_argument("--receipt", action="append", default=[])
    f.add_argument("--output", required=True)
    f.add_argument("--markdown-output", required=True)
    args = p.parse_args()

    if args.command == "apply":
        receipt = apply_profile(Path(args.provider_root), args.canonical_id, args.provider)
        save(args.receipt, receipt)
    elif args.command == "plan":
        save(args.output, build_repair_plan(load(args.b3_plan)))
    else:
        report = finalize(
            load(args.b3_plan), load(args.candidate_profile), load(args.lkg_profile),
            load(args.candidate_live), load(args.lkg_live), load(args.repaired_live),
            [load(path) for path in args.receipt],
        )
        save(args.output, report)
        Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
