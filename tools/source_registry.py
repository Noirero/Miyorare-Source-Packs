#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

LANGUAGES = {"id", "en"}
PROVIDERS = {"keiyoushi", "uma", "gekkoushi"}
AUTH_TYPES = {"NO_AUTH", "COOKIE", "FORM", "WEBVIEW", "TOKEN", "INTERACTIVE_REQUIRED", "UNSUPPORTED"}
CAPABILITIES = {"load", "browse", "search", "details", "chapters", "content", "authenticate", "download", "reader"}
UPDATE_STATES = {"CANDIDATE", "PROMOTED", "HELD"}
RUNTIME_STATES = {"HEALTHY", "DEGRADED", "BROKEN", "UNKNOWN"}
APPROVAL_STATES = {"NOT_READY", "WAITING_FOR_APPROVAL", "APPROVED", "REJECTED"}


class RegistryError(ValueError):
    pass


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _policy_ok(policy: object) -> bool:
    if not isinstance(policy, dict):
        return False
    return (
        policy.get("autoDiagnose") is True
        and policy.get("safeSelfRepair") is True
        and policy.get("keepLastKnownGood") is True
        and policy.get("validatedCanonicalFallback") is True
        and policy.get("holdRequiresOwnerAction") is False
    )


def validate_registry(registry: dict) -> None:
    if registry.get("schemaVersion") != 1:
        raise RegistryError("schemaVersion must be 1")
    scope = registry.get("scope", {})
    if set(scope.get("languages", [])) != LANGUAGES:
        raise RegistryError("scope languages must be id + en")
    if set(scope.get("providers", [])) != PROVIDERS:
        raise RegistryError("scope providers must be keiyoushi + uma + gekkoushi")

    provider_baselines = registry.get("providerBaselines", {})
    if set(provider_baselines) != PROVIDERS or not all(isinstance(v, str) and v for v in provider_baselines.values()):
        raise RegistryError("providerBaselines must define all providers")

    defaults = registry.get("defaults", {})
    if defaults.get("ownerActionRequired") is not False or not _policy_ok(defaults.get("repairPolicy")):
        raise RegistryError("defaults must preserve approve-only HOLD semantics")

    sources = registry.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RegistryError("sources must be non-empty")
    if scope.get("targetSize") != len(sources):
        raise RegistryError("targetSize must equal registry source count")

    ids: set[str] = set()
    languages = Counter()
    providers_seen: set[str] = set()
    families: set[str] = set()
    auth_seen: set[str] = set()

    for source in sources:
        canonical = source.get("canonicalId")
        if not isinstance(canonical, str) or not canonical or canonical in ids:
            raise RegistryError("canonicalId must be unique and non-empty")
        ids.add(canonical)

        language = source.get("language")
        if language not in LANGUAGES:
            raise RegistryError(f"invalid language for {canonical}")
        languages[language] += 1

        if source.get("contentProfile") not in {"manga", "novel"}:
            raise RegistryError(f"invalid content profile for {canonical}")
        auth = source.get("authType")
        if auth not in AUTH_TYPES:
            raise RegistryError(f"invalid auth type for {canonical}")
        auth_seen.add(auth)

        family = source.get("adapterFamily")
        if not isinstance(family, str) or not family:
            raise RegistryError(f"missing adapter family for {canonical}")
        families.add(family)

        provider_list = source.get("providers")
        if not isinstance(provider_list, list) or not provider_list:
            raise RegistryError(f"missing providers for {canonical}")
        provider_set = set(provider_list)
        if len(provider_set) != len(provider_list) or not provider_set <= PROVIDERS:
            raise RegistryError(f"invalid providers for {canonical}")
        providers_seen |= provider_set

        for key in ("upstreamIdentities", "currentVersion", "lastKnownGood"):
            value = source.get(key)
            if not isinstance(value, dict) or set(value) != provider_set:
                raise RegistryError(f"{key} must match providers for {canonical}")

        for provider in provider_set:
            identity = source["upstreamIdentities"][provider]
            if not isinstance(identity, dict) or not identity.get("sourceName"):
                raise RegistryError(f"invalid {provider} identity for {canonical}")
            locator = identity.get("module") if provider == "keiyoushi" else identity.get("file")
            if not isinstance(locator, str) or not locator:
                raise RegistryError(f"missing {provider} locator for {canonical}")
            if provider == "keiyoushi" and not isinstance(identity.get("sourceId"), int):
                raise RegistryError(f"missing Keiyoushi sourceId for {canonical}")
            if source["currentVersion"][provider] != provider_baselines[provider]:
                raise RegistryError(f"currentVersion baseline mismatch for {canonical}")
            if source["lastKnownGood"][provider] != provider_baselines[provider]:
                raise RegistryError(f"lastKnownGood baseline mismatch for {canonical}")

        if source.get("updateState") not in UPDATE_STATES:
            raise RegistryError(f"invalid update state for {canonical}")
        if source.get("runtimeHealth") not in RUNTIME_STATES:
            raise RegistryError(f"invalid runtime health for {canonical}")
        if source.get("approvalState") not in APPROVAL_STATES:
            raise RegistryError(f"invalid approval state for {canonical}")
        if not isinstance(source.get("healthyHistory"), list):
            raise RegistryError(f"healthyHistory must be a list for {canonical}")
        if not _policy_ok(source.get("repairPolicy")):
            raise RegistryError(f"repair policy violates approve-only semantics for {canonical}")

        baseline = source.get("compatibilityBaseline", {})
        capabilities = baseline.get("capabilities")
        if baseline.get("status") != "PENDING" or not isinstance(capabilities, list) or set(capabilities) != CAPABILITIES:
            raise RegistryError(f"invalid compatibility baseline for {canonical}")
        if not isinstance(source.get("selectionReasons"), list) or not source["selectionReasons"]:
            raise RegistryError(f"selection reasons required for {canonical}")

    if providers_seen != PROVIDERS:
        raise RegistryError("seed cohort must exercise all providers")
    if languages["id"] < 5 or languages["en"] < 5:
        raise RegistryError("seed cohort must include at least five ID and five EN sources")
    if len(families) < 6:
        raise RegistryError("seed cohort must exercise at least six adapter families")
    if not {"NO_AUTH", "COOKIE"} <= auth_seen:
        raise RegistryError("seed cohort must include no-auth and cookie-auth paths")


def summary(registry: dict) -> dict:
    validate_registry(registry)
    sources = registry["sources"]
    return {
        "cohort": registry["scope"]["cohort"],
        "sourceCount": len(sources),
        "languages": dict(Counter(s["language"] for s in sources)),
        "providerMemberships": dict(Counter(p for s in sources for p in s["providers"])),
        "adapterFamilies": sorted({s["adapterFamily"] for s in sources}),
        "authTypes": sorted({s["authType"] for s in sources}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "summary"))
    parser.add_argument("--registry", default="compatibility/source-registry.json")
    args = parser.parse_args()
    registry = load_json(args.registry)
    if args.command == "validate":
        validate_registry(registry)
        print("source registry: valid")
    else:
        print(json.dumps(summary(registry), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
