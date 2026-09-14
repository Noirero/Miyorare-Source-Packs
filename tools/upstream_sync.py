#!/usr/bin/env python3
"""Miyorare Source Pack upstream synchronization helpers.

The sync engine separates upstream detection, compatibility materialization, overlay conflict tracking,
and promotion. Provider-wide revisions can advance only after CI validation, while protected Miyorare
overlays keep their own reconciliation base so one conflicting source does not force unrelated sources
to remain on an old provider revision.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

HEX40 = re.compile(r"^[0-9a-f]{40}$")
SUPPORTED_POLICIES = {"adapt-validate", "compatibility-layer", "three-way-overlay"}


def fail(message: str, code: int = 1) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"could not read {path}: {exc}")
    if not isinstance(value, dict):
        fail(f"{path} must contain a JSON object")
    return value


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def registry_providers(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    providers = registry.get("providers")
    if not isinstance(providers, dict) or not providers:
        fail("registry.providers must be a non-empty object")
    return providers


def validate_registry(registry: dict[str, Any]) -> None:
    if registry.get("schema") != 1:
        fail("unsupported upstream registry schema")

    miyorare = registry.get("miyorare")
    if not isinstance(miyorare, dict):
        fail("registry.miyorare is required")
    for key in ("repository", "branch", "packsManifest", "aliasManifest", "overlayRoot"):
        if not isinstance(miyorare.get(key), str) or not miyorare[key].strip():
            fail(f"registry.miyorare.{key} is required")

    policy = registry.get("policy")
    if not isinstance(policy, dict):
        fail("registry.policy is required")
    required_bools = (
        "autoUpdateByDefault",
        "manualOnlyOnIncompatibility",
        "publishOnlyAfterValidation",
        "keepLastKnownGoodOnFailure",
        "perSourceFailSafe",
        "protectMiyorareCustomization",
    )
    for key in required_bools:
        if policy.get(key) is not True:
            fail(f"registry.policy.{key} must stay true")

    protected = registry.get("protectedAreas")
    if not isinstance(protected, list) or not protected or not all(isinstance(item, str) and item for item in protected):
        fail("registry.protectedAreas must be a non-empty string list")

    providers = registry_providers(registry)
    required = {"keiyoushi", "uma", "gekkoushi"}
    missing = sorted(required - set(providers))
    if missing:
        fail("missing required provider(s): " + ", ".join(missing))

    for name, provider in providers.items():
        if not isinstance(provider, dict):
            fail(f"provider {name} must be an object")
        for key in ("repository", "branch", "license", "policy", "upstreamBase", "lastKnownGood"):
            if not isinstance(provider.get(key), str) or not provider[key].strip():
                fail(f"provider {name}.{key} is required")
        if provider["policy"] not in SUPPORTED_POLICIES:
            fail(f"provider {name} has unsupported policy {provider['policy']!r}")
        for key in ("upstreamBase", "lastKnownGood"):
            if not HEX40.fullmatch(provider[key]):
                fail(f"provider {name}.{key} must be a 40-character git SHA")
        if provider.get("autoPromote") is not True:
            fail(f"provider {name}.autoPromote must stay true")

        targets = provider.get("protectedOverlayTargets", [])
        if not isinstance(targets, list) or not all(isinstance(item, str) and item for item in targets):
            fail(f"provider {name}.protectedOverlayTargets must be a string list")

        overlay_bases = provider.get("overlayBases", {})
        if not isinstance(overlay_bases, dict):
            fail(f"provider {name}.overlayBases must be an object")
        unknown_bases = sorted(set(overlay_bases) - set(targets))
        if unknown_bases:
            fail(f"provider {name}.overlayBases contains unknown protected target(s): {', '.join(unknown_bases)}")
        for target, sha in overlay_bases.items():
            if not isinstance(target, str) or not target:
                fail(f"provider {name}.overlayBases has an invalid target")
            if not isinstance(sha, str) or not HEX40.fullmatch(sha):
                fail(f"provider {name}.overlayBases[{target!r}] must be a 40-character git SHA")


def remote_head(repository: str, branch: str) -> str:
    url = f"https://github.com/{repository}.git"
    try:
        out = subprocess.check_output(
            ["git", "ls-remote", url, f"refs/heads/{branch}"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=60,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        fail(f"could not resolve {repository}@{branch}: {exc}")
    if not out:
        fail(f"no branch head returned for {repository}@{branch}")
    sha = out.split()[0]
    if not HEX40.fullmatch(sha):
        fail(f"invalid branch head for {repository}@{branch}: {sha!r}")
    return sha


def make_plan(registry: dict[str, Any]) -> dict[str, Any]:
    validate_registry(registry)
    providers_out: dict[str, Any] = {}
    for name, provider in registry_providers(registry).items():
        candidate = remote_head(provider["repository"], provider["branch"])
        current = provider["lastKnownGood"]
        providers_out[name] = {
            "repository": provider["repository"],
            "branch": provider["branch"],
            "policy": provider["policy"],
            "upstreamBase": provider["upstreamBase"],
            "lastKnownGood": current,
            "candidate": candidate,
            "changed": candidate != current,
            "state": "candidate" if candidate != current else "synced",
        }
    return {"schema": 1, "providers": providers_out}


def write_github_outputs(plan: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    for name, item in plan["providers"].items():
        prefix = name.upper().replace("-", "_")
        lines.extend(
            [
                f"{prefix}_CURRENT={item['lastKnownGood']}",
                f"{prefix}_CANDIDATE={item['candidate']}",
                f"{prefix}_CHANGED={'true' if item['changed'] else 'false'}",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def apply_registry_pins(
    registry: dict[str, Any],
    miyorare_root: Path,
    overrides: dict[str, str],
) -> None:
    validate_registry(registry)
    providers = registry_providers(registry)
    pins = {name: overrides.get(name, provider["lastKnownGood"]) for name, provider in providers.items()}
    for name, sha in pins.items():
        if not HEX40.fullmatch(sha):
            fail(f"override for {name} is not a 40-character SHA")

    cfg = registry["miyorare"]
    packs_path = miyorare_root / cfg["packsManifest"]
    aliases_path = miyorare_root / cfg["aliasManifest"]
    packs = load_json(packs_path)
    aliases = load_json(aliases_path)

    upstream = packs.setdefault("upstream", {})
    if upstream.get("repository") != providers["uma"]["repository"]:
        fail("packs.json UMA repository does not match registry")
    upstream["commit"] = pins["uma"]

    additional = packs.setdefault("additionalUpstreams", {})
    gek = additional.setdefault("gekkoushi", {})
    if gek.get("repository") != providers["gekkoushi"]["repository"]:
        fail("packs.json Gekkoushi repository does not match registry")
    gek["commit"] = pins["gekkoushi"]

    aliases_upstreams = aliases.setdefault("upstreams", {})
    for name in ("uma", "keiyoushi"):
        meta = aliases_upstreams.setdefault(name, {})
        if meta.get("repository") != providers[name]["repository"]:
            fail(f"multi-upstream.json {name} repository does not match registry")
        meta["commit"] = pins[name]

    save_json(packs_path, packs)
    save_json(aliases_path, aliases)


def parse_overrides(values: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            fail(f"override must use provider=sha: {raw!r}")
        provider, sha = raw.split("=", 1)
        provider = provider.strip()
        sha = sha.strip().lower()
        if provider in overrides:
            fail(f"duplicate override for {provider}")
        overrides[provider] = sha
    return overrides


def ensure_git_commits(repo: Path, *commits: str) -> None:
    for commit in commits:
        if not HEX40.fullmatch(commit):
            fail(f"invalid git SHA: {commit!r}")
    try:
        subprocess.run(
            ["git", "-C", str(repo), "fetch", "--no-tags", "origin", *commits],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        fail(f"could not fetch upstream commits in {repo}: {exc}")


def git_changed_files(repo: Path, base: str, candidate: str) -> set[str]:
    ensure_git_commits(repo, base, candidate)
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "diff", "--name-only", f"{base}..{candidate}"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=60,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        fail(f"could not compare upstream commits in {repo}: {exc}")
    return {line.strip() for line in out.splitlines() if line.strip()}


def git_path_changed(repo: Path, base: str, candidate: str, path: str) -> bool:
    ensure_git_commits(repo, base, candidate)
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "diff", "--quiet", f"{base}..{candidate}", "--", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        fail(f"could not compare protected target {path} in {repo}: {exc}")
    if completed.returncode == 0:
        return False
    if completed.returncode == 1:
        return True
    fail(f"git diff failed for protected target {path}: {completed.stderr.strip()}")


def overlay_targets(registry: dict[str, Any], miyorare_root: Path, provider_name: str) -> set[str]:
    provider = registry_providers(registry)[provider_name]
    targets = set(provider.get("protectedOverlayTargets", []))
    overlay_root = miyorare_root / registry["miyorare"]["overlayRoot"] / provider_name
    if overlay_root.is_dir():
        for path in overlay_root.rglob("*.kt"):
            relative = path.relative_to(overlay_root)
            targets.add((Path("src/main/kotlin/tsuki/site") / relative).as_posix())
    return targets


def check_overlay_conflicts(
    registry: dict[str, Any],
    miyorare_root: Path,
    upstream_repo: Path,
    provider_name: str,
    base: str,
    candidate: str,
    output: Path | None,
    strict: bool,
) -> None:
    validate_registry(registry)
    provider = registry_providers(registry).get(provider_name)
    if provider is None:
        fail(f"unknown provider {provider_name}")
    if provider["policy"] != "three-way-overlay":
        fail(f"overlay conflict check is only valid for three-way-overlay providers, got {provider['policy']}")

    changed = git_changed_files(upstream_repo, base, candidate)
    protected = overlay_targets(registry, miyorare_root, provider_name)
    overlay_bases = provider.get("overlayBases", {})
    conflicts: list[str] = []
    conflict_details: list[dict[str, str]] = []

    for target in sorted(protected):
        target_base = overlay_bases.get(target, base)
        if git_path_changed(upstream_repo, target_base, candidate, target):
            conflicts.append(target)
            conflict_details.append(
                {
                    "target": target,
                    "overlayBase": target_base,
                    "candidate": candidate,
                    "state": "held-by-miyorare-overlay",
                }
            )

    report = {
        "schema": 2,
        "provider": provider_name,
        "base": base,
        "candidate": candidate,
        "changedFileCount": len(changed),
        "protectedTargets": sorted(protected),
        "conflicts": conflicts,
        "conflictDetails": conflict_details,
        "state": "partial-hold" if conflicts else "clear",
        "providerMayAdvance": True,
    }
    if output:
        save_json(output, report)
    print(json.dumps(report, indent=2))

    if strict and conflicts:
        fail(
            "candidate touches protected Miyorare overlay target(s): " + ", ".join(conflicts),
            code=3,
        )


def promote(registry_path: Path, provider_name: str, commit: str) -> None:
    registry = load_json(registry_path)
    validate_registry(registry)
    providers = registry_providers(registry)
    if provider_name not in providers:
        fail(f"unknown provider {provider_name}")
    if not HEX40.fullmatch(commit):
        fail("promotion commit must be a 40-character git SHA")
    provider = providers[provider_name]
    provider["upstreamBase"] = commit
    provider["lastKnownGood"] = commit
    save_json(registry_path, registry)


def promote_overlay_base(registry_path: Path, provider_name: str, target: str, commit: str) -> None:
    registry = load_json(registry_path)
    validate_registry(registry)
    providers = registry_providers(registry)
    provider = providers.get(provider_name)
    if provider is None:
        fail(f"unknown provider {provider_name}")
    if provider["policy"] != "three-way-overlay":
        fail("overlay base promotion is only valid for three-way-overlay providers")
    targets = set(provider.get("protectedOverlayTargets", []))
    if target not in targets:
        fail(f"target is not registered as protected overlay: {target}")
    if not HEX40.fullmatch(commit):
        fail("overlay base promotion commit must be a 40-character git SHA")
    provider.setdefault("overlayBases", {})[target] = commit
    save_json(registry_path, registry)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--registry", type=Path, required=True)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--registry", type=Path, required=True)
    p_plan.add_argument("--output", type=Path, required=True)
    p_plan.add_argument("--github-output", type=Path)

    p_materialize = sub.add_parser("materialize")
    p_materialize.add_argument("--registry", type=Path, required=True)
    p_materialize.add_argument("--miyorare-root", type=Path, required=True)
    p_materialize.add_argument("--override", action="append", default=[])

    p_conflicts = sub.add_parser("overlay-conflicts")
    p_conflicts.add_argument("--registry", type=Path, required=True)
    p_conflicts.add_argument("--miyorare-root", type=Path, required=True)
    p_conflicts.add_argument("--upstream-repo", type=Path, required=True)
    p_conflicts.add_argument("--provider", required=True)
    p_conflicts.add_argument("--base", required=True)
    p_conflicts.add_argument("--candidate", required=True)
    p_conflicts.add_argument("--output", type=Path)
    p_conflicts.add_argument("--strict", action="store_true")

    p_promote = sub.add_parser("promote")
    p_promote.add_argument("--registry", type=Path, required=True)
    p_promote.add_argument("--provider", required=True)
    p_promote.add_argument("--commit", required=True)

    p_promote_overlay = sub.add_parser("promote-overlay-base")
    p_promote_overlay.add_argument("--registry", type=Path, required=True)
    p_promote_overlay.add_argument("--provider", required=True)
    p_promote_overlay.add_argument("--target", required=True)
    p_promote_overlay.add_argument("--commit", required=True)

    args = parser.parse_args()
    registry_path = args.registry.resolve()

    if args.command == "validate":
        registry = load_json(registry_path)
        validate_registry(registry)
        print("upstream registry is valid")
    elif args.command == "plan":
        registry = load_json(registry_path)
        plan = make_plan(registry)
        save_json(args.output.resolve(), plan)
        if args.github_output:
            write_github_outputs(plan, args.github_output.resolve())
        print(json.dumps(plan, indent=2))
    elif args.command == "materialize":
        registry = load_json(registry_path)
        apply_registry_pins(registry, args.miyorare_root.resolve(), parse_overrides(args.override))
    elif args.command == "overlay-conflicts":
        registry = load_json(registry_path)
        check_overlay_conflicts(
            registry=registry,
            miyorare_root=args.miyorare_root.resolve(),
            upstream_repo=args.upstream_repo.resolve(),
            provider_name=args.provider,
            base=args.base,
            candidate=args.candidate,
            output=args.output.resolve() if args.output else None,
            strict=args.strict,
        )
    elif args.command == "promote":
        promote(registry_path, args.provider, args.commit.lower())
    elif args.command == "promote-overlay-base":
        promote_overlay_base(registry_path, args.provider, args.target, args.commit.lower())
    else:
        fail(f"unsupported command {args.command}")


if __name__ == "__main__":
    main()
