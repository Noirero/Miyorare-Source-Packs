#!/usr/bin/env python3
"""Build and validate the informational Miyorare source inventory.

The inventory is intentionally separate from Compatibility Farm membership. It
only describes sources discovered in upstream provider repositories and stable
canonical mappings. Privileged enrollment/promotion remains owned by the Farm.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
PARSER_RE = re.compile(
    r'@MangaSourceParser\(\s*"([^"]+)"\s*,\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?'
)
ASSIGN_STRING_RE = re.compile(r'\b({name})\s*=\s*"([^"]*)"')
ASSIGN_INT_RE = re.compile(r'\b({name})\s*=\s*(-?\d+)')
SOURCE_BLOCK_RE = re.compile(r'\bsource\s*\{')


def load_json(path: Path | None, default: Any) -> Any:
    if path is None or not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def normalize_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def safe_lang(value: str | None, fallback: str = "unknown") -> str:
    raw = (value or "").strip().lower()
    return raw if re.fullmatch(r"[a-z0-9-]{1,16}", raw) else fallback


def compute_keiyoushi_source_id(name: str, lang: str, version_id: int = 1) -> int:
    key = f"{name.lower()}/{lang}/{version_id}".encode()
    digest = hashlib.md5(key).digest()
    value = 0
    for byte in digest[:8]:
        value = (value << 8) | byte
    return value & ((1 << 63) - 1)


def find_matching_brace(text: str, open_index: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(open_index, len(text)):
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def blocks(text: str, pattern: re.Pattern[str]) -> Iterable[str]:
    for match in pattern.finditer(text):
        open_index = text.find("{", match.start())
        if open_index < 0:
            continue
        close_index = find_matching_brace(text, open_index)
        if close_index is not None:
            yield text[open_index + 1 : close_index]


def assign_string(text: str, name: str) -> str | None:
    match = re.search(ASSIGN_STRING_RE.pattern.format(name=re.escape(name)), text)
    return match.group(2) if match else None


def assign_int(text: str, name: str) -> int | None:
    match = re.search(ASSIGN_INT_RE.pattern.format(name=re.escape(name)), text)
    return int(match.group(2)) if match else None


def provider_identity(provider: str, mapping: dict[str, Any]) -> str:
    if provider == "keiyoushi":
        return f"module:{mapping.get('module', '')}|sourceId:{mapping.get('sourceId', '')}"
    return f"file:{mapping.get('file', '')}|sourceName:{mapping.get('sourceName', '')}"


def record(provider: str, source_name: str, lang: str, mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": provider,
        "sourceName": source_name.strip() or Path(str(mapping.get("file") or mapping.get("module") or provider)).stem,
        "language": safe_lang(lang),
        "mapping": mapping,
    }


def discover_keiyoushi(root: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    src = root / "src"
    if not src.is_dir():
        return found
    for gradle in sorted(src.glob("*/*/build.gradle.kts")):
        module = gradle.parent.relative_to(root).as_posix()
        text = gradle.read_text(encoding="utf-8", errors="replace")
        outer_name = assign_string(text, "name") or gradle.parent.name
        version_code = assign_int(text, "versionCode")
        source_blocks = list(blocks(text, SOURCE_BLOCK_RE))
        if not source_blocks:
            lang = gradle.parent.parent.name
            mapping = {"available": True, "module": module, "sourceName": outer_name}
            if version_code is not None:
                mapping["extensionVersionCode"] = version_code
            found.append(record("keiyoushi", outer_name, lang, mapping))
            continue
        for source_block in source_blocks:
            name = assign_string(source_block, "name") or outer_name
            lang = assign_string(source_block, "lang") or gradle.parent.parent.name
            explicit_id = assign_int(source_block, "id")
            version_id = assign_int(source_block, "versionId") or 1
            source_id = explicit_id if explicit_id is not None else compute_keiyoushi_source_id(name, lang, version_id)
            mapping: dict[str, Any] = {
                "available": True,
                "module": module,
                "sourceName": name,
                "sourceId": source_id,
            }
            if version_id != 1:
                mapping["versionId"] = version_id
            if version_code is not None:
                mapping["extensionVersionCode"] = version_code
            base_url = assign_string(source_block, "baseUrl")
            if base_url:
                mapping["baseUrl"] = base_url
            found.append(record("keiyoushi", name, lang, mapping))
    return found


def discover_tsuki(provider: str, root: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    base = root / "src/main/kotlin/tsuki/site"
    if not base.is_dir():
        return found
    for file in sorted(base.rglob("*.kt")):
        text = file.read_text(encoding="utf-8", errors="replace")
        rel = file.relative_to(root).as_posix()
        for match in PARSER_RE.finditer(text):
            parser_id, name, lang = match.group(1), match.group(2), match.group(3)
            inferred_lang = file.relative_to(base).parts[0] if file.relative_to(base).parts else "unknown"
            found.append(
                record(
                    provider,
                    name,
                    lang or inferred_lang,
                    {
                        "available": True,
                        "sourceName": parser_id,
                        "displayName": name,
                        "file": rel,
                    },
                )
            )
    return found


def explicit_mappings(aliases: dict[str, Any], farm: dict[str, Any]) -> tuple[dict[tuple[str, str], str], dict[str, dict[str, Any]]]:
    identity_to_canonical: dict[tuple[str, str], str] = {}
    metadata: dict[str, dict[str, Any]] = {}

    def register(canonical: str, language: str | None, display: str | None, provider: str, mapping: dict[str, Any]) -> None:
        identity_to_canonical[(provider, provider_identity(provider, mapping))] = canonical
        entry = metadata.setdefault(canonical, {})
        if language and not entry.get("language"):
            entry["language"] = safe_lang(language)
        if display and not entry.get("displayName"):
            entry["displayName"] = display

    for item in aliases.get("aliases", []):
        if not isinstance(item, dict) or not isinstance(item.get("canonicalId"), str):
            continue
        canonical = item["canonicalId"]
        official = item.get("official") if isinstance(item.get("official"), dict) else {}
        for provider in PROVIDERS:
            mapping = item.get(provider)
            if isinstance(mapping, dict):
                register(canonical, item.get("language"), official.get("sourceName"), provider, mapping)

    for item in farm.get("sources", []):
        if not isinstance(item, dict) or not isinstance(item.get("canonicalId"), str):
            continue
        canonical = item["canonicalId"]
        identities = item.get("upstreamIdentities")
        if not isinstance(identities, dict):
            continue
        for provider, mapping in identities.items():
            if provider in PROVIDERS and isinstance(mapping, dict):
                register(canonical, item.get("language"), item.get("displayName"), provider, mapping)
    return identity_to_canonical, metadata


def previous_mappings(previous: dict[str, Any]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for source in previous.get("sources", []):
        if not isinstance(source, dict) or not isinstance(source.get("canonicalId"), str):
            continue
        mappings = source.get("providers")
        if not isinstance(mappings, dict):
            continue
        for provider, mapping in mappings.items():
            if provider in PROVIDERS and isinstance(mapping, dict):
                result[(provider, provider_identity(provider, mapping))] = source["canonicalId"]
    return result


def fallback_canonical(lang: str, name: str) -> str:
    normalized = normalize_name(name) or "UNKNOWN"
    return f"miyorare:inventory-{safe_lang(lang)}:{normalized}"


def provider_scoped_canonical(item: dict[str, Any]) -> str:
    provider = item["provider"]
    identity = provider_identity(provider, item["mapping"])
    suffix = hashlib.sha256(identity.encode()).hexdigest()[:10].upper()
    base = fallback_canonical(item["language"], item["sourceName"])
    return f"{base}:{provider.upper()}-{suffix}"


def build_inventory(
    keiyoushi_root: Path,
    uma_root: Path,
    gekkoushi_root: Path,
    aliases: dict[str, Any],
    farm: dict[str, Any],
    previous: dict[str, Any],
    provider_commits: dict[str, str],
) -> dict[str, Any]:
    raw = [
        *discover_keiyoushi(keiyoushi_root),
        *discover_tsuki("uma", uma_root),
        *discover_tsuki("gekkoushi", gekkoushi_root),
    ]
    explicit, canonical_metadata = explicit_mappings(aliases, farm)
    prior = previous_mappings(previous)

    assigned: dict[int, tuple[str, str]] = {}
    for index, item in enumerate(raw):
        key = (item["provider"], provider_identity(item["provider"], item["mapping"]))
        if key in explicit:
            assigned[index] = (explicit[key], "explicit")
        elif key in prior:
            assigned[index] = (prior[key], "previous")

    unmatched_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, item in enumerate(raw):
        if index not in assigned:
            unmatched_groups[(item["language"], normalize_name(item["sourceName"]))].append(index)

    for _, indexes in unmatched_groups.items():
        providers = [raw[index]["provider"] for index in indexes]
        collision = len(providers) != len(set(providers)) or not normalize_name(raw[indexes[0]]["sourceName"])
        if collision:
            for index in indexes:
                assigned[index] = (provider_scoped_canonical(raw[index]), "ambiguous")
        else:
            canonical = fallback_canonical(raw[indexes[0]]["language"], raw[indexes[0]]["sourceName"])
            for index in indexes:
                assigned[index] = (canonical, "exact-name")

    grouped: dict[str, list[tuple[dict[str, Any], str]]] = defaultdict(list)
    for index, item in enumerate(raw):
        canonical, confidence = assigned[index]
        grouped[canonical].append((item, confidence))

    sources: list[dict[str, Any]] = []
    for canonical in sorted(grouped):
        items = grouped[canonical]
        languages = {item["language"] for item, _ in items}
        explicit_meta = canonical_metadata.get(canonical, {})
        language = explicit_meta.get("language") or (next(iter(languages)) if len(languages) == 1 else "unknown")
        display = explicit_meta.get("displayName") or sorted(
            (item["sourceName"] for item, _ in items), key=lambda value: (len(value), value.lower())
        )[0]
        providers: dict[str, Any] = {}
        confidences = set()
        needs_attention = len(languages) > 1
        reasons: list[str] = []
        for item, confidence in items:
            provider = item["provider"]
            confidences.add(confidence)
            if provider in providers:
                needs_attention = True
                reasons.append(f"duplicate-{provider}-identity")
                continue
            providers[provider] = item["mapping"]
            if confidence == "ambiguous":
                needs_attention = True
                reasons.append("ambiguous-automatic-identity")
        if len(languages) > 1:
            reasons.append("language-mismatch")
        confidence = (
            "explicit" if "explicit" in confidences else
            "previous" if "previous" in confidences else
            "exact-name" if confidences == {"exact-name"} else
            "ambiguous"
        )
        sources.append(
            {
                "canonicalId": canonical,
                "displayName": display,
                "language": language,
                "identityConfidence": confidence,
                "needsAttention": needs_attention,
                "attentionReasons": sorted(set(reasons)),
                "providers": {provider: providers[provider] for provider in PROVIDERS if provider in providers},
            }
        )

    return {
        "schemaVersion": 1,
        "kind": "MIYORARE_SOURCE_INVENTORY",
        "informationalOnly": True,
        "providerSnapshots": {
            provider: {"commit": provider_commits.get(provider, "")}
            for provider in PROVIDERS
        },
        "stats": {
            "allSources": len(sources),
            "providerMappings": sum(len(source["providers"]) for source in sources),
            "needsAttention": sum(1 for source in sources if source["needsAttention"]),
        },
        "sources": sources,
    }


def validate_inventory(value: dict[str, Any]) -> None:
    if value.get("schemaVersion") != 1 or value.get("kind") != "MIYORARE_SOURCE_INVENTORY":
        raise ValueError("unsupported source inventory schema")
    if value.get("informationalOnly") is not True:
        raise ValueError("inventory must remain informationalOnly=true")
    sources = value.get("sources")
    if not isinstance(sources, list):
        raise ValueError("sources must be a list")
    canonical_seen: set[str] = set()
    provider_identity_seen: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("source entry must be an object")
        canonical = source.get("canonicalId")
        if not isinstance(canonical, str) or not canonical.startswith("miyorare:"):
            raise ValueError("source canonicalId is invalid")
        if canonical in canonical_seen:
            raise ValueError(f"duplicate canonicalId: {canonical}")
        canonical_seen.add(canonical)
        providers = source.get("providers")
        if not isinstance(providers, dict) or not providers:
            raise ValueError(f"{canonical} has no provider mappings")
        for provider, mapping in providers.items():
            if provider not in PROVIDERS or not isinstance(mapping, dict):
                raise ValueError(f"{canonical} has invalid provider mapping")
            key = (provider, provider_identity(provider, mapping))
            if key in provider_identity_seen:
                raise ValueError(f"provider identity appears in more than one canonical source: {key}")
            provider_identity_seen.add(key)
    stats = value.get("stats", {})
    if stats.get("allSources") != len(sources):
        raise ValueError("stats.allSources mismatch")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--keiyoushi-root", type=Path, required=True)
    build.add_argument("--uma-root", type=Path, required=True)
    build.add_argument("--gekkoushi-root", type=Path, required=True)
    build.add_argument("--aliases", type=Path, required=True)
    build.add_argument("--farm-registry", type=Path, required=True)
    build.add_argument("--previous", type=Path)
    build.add_argument("--keiyoushi-commit", required=True)
    build.add_argument("--uma-commit", required=True)
    build.add_argument("--gekkoushi-commit", required=True)
    build.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "build":
        value = build_inventory(
            args.keiyoushi_root,
            args.uma_root,
            args.gekkoushi_root,
            load_json(args.aliases, {}),
            load_json(args.farm_registry, {}),
            load_json(args.previous, {}),
            {
                "keiyoushi": args.keiyoushi_commit,
                "uma": args.uma_commit,
                "gekkoushi": args.gekkoushi_commit,
            },
        )
        validate_inventory(value)
        write_json(args.output, value)
    else:
        validate_inventory(load_json(args.inventory, {}))


if __name__ == "__main__":
    main()
