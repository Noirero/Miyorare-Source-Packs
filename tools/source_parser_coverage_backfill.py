#!/usr/bin/env python3
"""Backfill parser-family coverage for already-approved ACTIVE source memberships.

This tool is intentionally narrow and fail-closed. It does not approve sources, mutate
provider baselines, change pending-worker states, or touch Last-Known-Good state. It only
materializes parser-family declarations and reusable harness sources from parser evidence
that already passed during owner-approved PENDING source onboarding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import source_live_parser_harness as live_harness  # noqa: E402


class CoverageBackfillError(ValueError):
    pass


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CoverageBackfillError(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _source_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = registry.get("sources")
    if not isinstance(rows, list):
        raise CoverageBackfillError("registry.sources must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        canonical_id = row.get("canonicalId") if isinstance(row, dict) else None
        if not isinstance(canonical_id, str) or not canonical_id:
            raise CoverageBackfillError("registry source missing canonicalId")
        if canonical_id in result:
            raise CoverageBackfillError(f"duplicate canonicalId: {canonical_id}")
        result[canonical_id] = row
    return result


def _full_parser_pass(item: dict[str, Any]) -> bool:
    return (
        item.get("status") == "PASS"
        and item.get("parserExecution") is True
        and item.get("detailsTraversal") is True
        and item.get("chapterTraversal") is True
        and item.get("pageExtraction") is True
    )


def _family_memberships(families: dict[str, Any]) -> set[tuple[str, str]]:
    rows = families.get("families")
    if not isinstance(rows, list):
        raise CoverageBackfillError("parser families must contain a families list")
    result: set[tuple[str, str]] = set()
    for family in rows:
        if not isinstance(family, dict):
            raise CoverageBackfillError("parser family entry must be an object")
        provider = family.get("provider")
        members = family.get("members")
        if not isinstance(provider, str) or not isinstance(members, list):
            raise CoverageBackfillError("parser family provider/members invalid")
        for member in members:
            canonical_id = member.get("canonicalId") if isinstance(member, dict) else None
            if not isinstance(canonical_id, str) or not canonical_id:
                raise CoverageBackfillError("parser family member missing canonicalId")
            result.add((provider, canonical_id))
    return result


def _required_active_memberships(registry: dict[str, Any]) -> set[tuple[str, str]]:
    required: set[tuple[str, str]] = set()
    for canonical_id, source in _source_map(registry).items():
        enrollment = source.get("compatibilityEnrollment")
        if not isinstance(enrollment, dict):
            continue
        if enrollment.get("state") != "ACTIVE":
            continue
        if enrollment.get("parserCoverageRequired") is not True:
            raise CoverageBackfillError(
                f"{canonical_id}: ACTIVE enrollment must require parser coverage"
            )
        providers = source.get("providers")
        if not isinstance(providers, list) or not providers:
            raise CoverageBackfillError(f"{canonical_id}: ACTIVE source providers invalid")
        for provider in providers:
            if not isinstance(provider, str) or not provider:
                raise CoverageBackfillError(f"{canonical_id}: provider invalid")
            required.add((provider, canonical_id))
    return required


def _approved_worker_entry(
    state: dict[str, Any], canonical_id: str
) -> dict[str, Any]:
    sources = state.get("sources")
    entry = sources.get(canonical_id) if isinstance(sources, dict) else None
    if not isinstance(entry, dict):
        raise CoverageBackfillError(f"{canonical_id}: pending-worker evidence missing")
    if entry.get("state") != "APPROVED" or entry.get("approvalState") != "APPROVED":
        raise CoverageBackfillError(f"{canonical_id}: worker evidence is not APPROVED")
    return entry


def _approved_registry_source(source: dict[str, Any]) -> None:
    canonical_id = source["canonicalId"]
    approval = source.get("onboardingApproval")
    if not isinstance(approval, dict) or approval.get("state") != "APPROVED":
        raise CoverageBackfillError(f"{canonical_id}: owner onboarding approval missing")


def _provider_evidence(entry: dict[str, Any], provider: str) -> dict[str, Any]:
    evidence = entry.get("evidence")
    parser = evidence.get("parser") if isinstance(evidence, dict) else None
    rows = parser.get("memberships") if isinstance(parser, dict) else None
    if not isinstance(rows, list):
        raise CoverageBackfillError("approved worker parser memberships missing")
    matches = [row for row in rows if isinstance(row, dict) and row.get("provider") == provider]
    if len(matches) != 1:
        raise CoverageBackfillError(
            f"expected exactly one approved parser membership for provider {provider}, got {len(matches)}"
        )
    row = matches[0]
    if not _full_parser_pass(row):
        raise CoverageBackfillError(
            f"approved parser membership for provider {provider} is not a full real-parser PASS"
        )
    return row


def _profile_pass(entry: dict[str, Any], provider: str) -> None:
    evidence = entry.get("evidence")
    profile = evidence.get("profile") if isinstance(evidence, dict) else None
    rows = profile.get("memberships") if isinstance(profile, dict) else None
    if not isinstance(rows, list):
        raise CoverageBackfillError("approved worker profile memberships missing")
    matches = [row for row in rows if isinstance(row, dict) and row.get("provider") == provider]
    if len(matches) != 1 or matches[0].get("profilePass") is not True:
        raise CoverageBackfillError(f"approved profile membership for {provider} is not PASS")


def _test_class_parts(test_class: str) -> tuple[str, str]:
    package, sep, name = test_class.rpartition(".")
    if sep != "." or package != "compatibilityfarm" or not name:
        raise CoverageBackfillError(f"unsupported testClass: {test_class!r}")
    return package, name


def _stable_family_id(provider: str, canonical_id: str) -> str:
    digest = hashlib.sha256(f"{canonical_id}|{provider}".encode()).hexdigest()[:12]
    return f"{provider}-approved-live-{digest}"


def _write_exact(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing != content:
            raise CoverageBackfillError(f"refusing to overwrite different harness: {path}")
        return
    path.write_text(content, encoding="utf-8")


def backfill(
    registry: dict[str, Any],
    state: dict[str, Any],
    families: dict[str, Any],
    harness_root: Path,
    expected_missing_count: int | None = None,
) -> dict[str, Any]:
    sources = _source_map(registry)
    declared = _family_memberships(families)
    required = _required_active_memberships(registry)
    missing = sorted(required - declared)

    if expected_missing_count is not None and len(missing) != expected_missing_count:
        raise CoverageBackfillError(
            f"expected {expected_missing_count} missing ACTIVE memberships, found {len(missing)}"
        )

    added: list[dict[str, Any]] = []
    family_rows = families["families"]
    existing_family_ids = {
        row.get("id") for row in family_rows if isinstance(row, dict) and isinstance(row.get("id"), str)
    }

    for provider, canonical_id in missing:
        source = sources[canonical_id]
        _approved_registry_source(source)
        entry = _approved_worker_entry(state, canonical_id)
        _profile_pass(entry, provider)
        parser_row = _provider_evidence(entry, provider)

        tested = entry.get("testedVersions")
        current = source.get("currentVersion")
        if not isinstance(tested, dict) or not isinstance(current, dict):
            raise CoverageBackfillError(f"{canonical_id}: tested/current version binding missing")
        tested_sha = tested.get(provider)
        current_sha = current.get(provider)
        if not isinstance(tested_sha, str) or len(tested_sha) != 40 or tested_sha != current_sha:
            raise CoverageBackfillError(
                f"{canonical_id}@{provider}: approved parser evidence is not bound to current ACTIVE version"
            )

        adapter_family = source.get("adapterFamily")
        test_class = parser_row.get("testClass")
        if not isinstance(adapter_family, str) or not adapter_family:
            raise CoverageBackfillError(f"{canonical_id}: adapterFamily missing")
        if not isinstance(test_class, str):
            raise CoverageBackfillError(f"{canonical_id}@{provider}: testClass missing")
        _, class_name = _test_class_parts(test_class)

        family_id = _stable_family_id(provider, canonical_id)
        if family_id in existing_family_ids:
            raise CoverageBackfillError(f"family id already exists without membership: {family_id}")

        member: dict[str, Any] = {
            "canonicalId": canonical_id,
            "testClass": test_class,
        }
        if provider == "keiyoushi":
            identity = source.get("upstreamIdentities", {}).get(provider, {})
            module = identity.get("module") if isinstance(identity, dict) else None
            if not isinstance(module, str) or not module:
                raise CoverageBackfillError(f"{canonical_id}@keiyoushi: module missing")
            member["module"] = module
            harness_content = live_harness.keiyoushi_test_source(class_name)
            runner = "android-gradle-live-test"
        elif provider in {"uma", "gekkoushi"}:
            fqcn = parser_row.get("fqcn")
            if not isinstance(fqcn, str) or not fqcn:
                raise CoverageBackfillError(f"{canonical_id}@{provider}: proven parser fqcn missing")
            harness_content = live_harness.tsuki_test_source(class_name, fqcn)
            runner = "gradle-jvm-test"
            _write_exact(
                harness_root / provider / "LiveMangaLoaderContext.kt",
                live_harness.live_context_source(),
            )
        else:
            raise CoverageBackfillError(f"unsupported provider: {provider}")

        harness_path = harness_root / provider / f"{class_name}.kt"
        _write_exact(harness_path, harness_content)

        family = {
            "id": family_id,
            "provider": provider,
            "registryAdapterFamily": adapter_family,
            "providerParserFamily": "approved-live-parser",
            "runner": runner,
            "members": [member],
        }
        family_rows.append(family)
        existing_family_ids.add(family_id)
        added.append(
            {
                "canonicalId": canonical_id,
                "provider": provider,
                "familyId": family_id,
                "testClass": test_class,
                "harness": str(harness_path),
                "testedVersion": tested_sha,
            }
        )

    remaining = sorted(_required_active_memberships(registry) - _family_memberships(families))
    if remaining:
        rendered = ", ".join(f"{canonical}@{provider}" for provider, canonical in remaining)
        raise CoverageBackfillError(f"ACTIVE parser coverage still missing after backfill: {rendered}")

    return {
        "schemaVersion": 1,
        "action": "BACKFILL_APPROVED_ACTIVE_PARSER_COVERAGE",
        "missingBefore": len(missing),
        "addedMembershipCount": len(added),
        "remainingMissingCount": 0,
        "added": added,
        "mutatesRegistry": False,
        "mutatesPendingWorkerState": False,
        "mutatesProviderBaselines": False,
        "mutatesLastKnownGood": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--families", required=True)
    parser.add_argument("--harness-root", required=True)
    parser.add_argument("--expected-missing-count", type=int)
    parser.add_argument("--report", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    registry_path = Path(args.registry)
    state_path = Path(args.state)
    families_path = Path(args.families)

    registry = load(registry_path)
    state = load(state_path)
    families = load(families_path)
    report = backfill(
        registry,
        state,
        families,
        Path(args.harness_root),
        args.expected_missing_count,
    )
    save(families_path, families)
    save(args.report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
