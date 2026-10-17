#!/usr/bin/env python3
"""Cross-check a Miyorare Audio Pack catalog against exact Hiraukan manifests.

The Miyorare catalog is distribution metadata. Hiraukan's concrete
AudioExtensionManifest declarations are the runtime capability authority.
This validator fails closed on ID, version, auth, language, or capability drift.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

RUNTIME_FILES = {
    "miyorare.audio.asmr_one": "asmr_one_audio_extension.dart",
    "miyorare.audio.hentai_asmr": "hentai_asmr_audio_extension.dart",
    "miyorare.audio.japanese_asmr": "japanese_asmr_audio_extension.dart",
    "miyorare.audio.asmr18": "asmr18_audio_extension.dart",
    "miyorare.audio.ero_voice": "ero_voice_audio_extension.dart",
    "miyorare.audio.asmr_hentai_net": "asmr_hentai_net_audio_extension.dart",
}

MANIFEST_RE = re.compile(r"AudioExtensionManifest\s*\((.*?)\)\s*[,;]", re.DOTALL)
STRING_FIELD_RE = {
    "id": re.compile(r"\bid\s*:\s*'([^']+)'"),
    "name": re.compile(r"\bname\s*:\s*'([^']+)'"),
    "version": re.compile(r"\bversion\s*:\s*'([^']+)'"),
}
AUTH_RE = re.compile(r"\bauth\s*:\s*AudioExtensionAuthRequirement\.(\w+)")
CAPS_RE = re.compile(r"\bcapabilities\s*:\s*\{(.*?)\}", re.DOTALL)
CAP_RE = re.compile(r"AudioExtensionCapability\.(\w+)")
LANGS_RE = re.compile(r"\blanguages\s*:\s*\[(.*?)\]", re.DOTALL)
STRING_RE = re.compile(r"'([^']+)'\s*,?")


class RuntimeContractError(ValueError):
    pass


def _parse_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeContractError(f"missing Hiraukan runtime manifest file: {path}")
    text = path.read_text(encoding="utf-8")
    match = MANIFEST_RE.search(text)
    if match is None:
        raise RuntimeContractError(f"AudioExtensionManifest declaration not found: {path}")
    body = match.group(1)

    parsed: dict[str, Any] = {}
    for field, pattern in STRING_FIELD_RE.items():
        value = pattern.search(body)
        if value is None:
            raise RuntimeContractError(f"{path}: missing manifest {field}")
        parsed[field] = value.group(1)

    auth = AUTH_RE.search(body)
    if auth is None:
        raise RuntimeContractError(f"{path}: missing explicit auth declaration")
    parsed["auth"] = auth.group(1)

    caps = CAPS_RE.search(body)
    if caps is None:
        raise RuntimeContractError(f"{path}: missing explicit capabilities declaration")
    parsed["capabilities"] = set(CAP_RE.findall(caps.group(1)))
    if not parsed["capabilities"]:
        raise RuntimeContractError(f"{path}: empty capabilities declaration")

    langs = LANGS_RE.search(body)
    if langs is None:
        raise RuntimeContractError(f"{path}: missing explicit languages declaration")
    parsed["languages"] = [value for value in STRING_RE.findall(langs.group(1))]
    if not parsed["languages"]:
        raise RuntimeContractError(f"{path}: empty languages declaration")
    return parsed


def validate(catalog_path: Path, hiraukan_dir: Path) -> dict[str, Any]:
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    extensions = data.get("extensions")
    if not isinstance(extensions, list):
        raise RuntimeContractError("catalog extensions must be a list")

    catalog: dict[str, dict[str, Any]] = {}
    for item in extensions:
        if not isinstance(item, dict):
            raise RuntimeContractError("catalog extension entries must be objects")
        extension_id = item.get("id")
        if not isinstance(extension_id, str) or not extension_id:
            raise RuntimeContractError("catalog extension id is required")
        if extension_id in catalog:
            raise RuntimeContractError(f"duplicate catalog extension id: {extension_id}")
        catalog[extension_id] = item

    if set(catalog) != set(RUNTIME_FILES):
        raise RuntimeContractError(
            "catalog runtime set differs from exact six Hiraukan audio runtimes"
        )

    root = hiraukan_dir / "lib" / "src" / "extensions"
    checked = []
    for extension_id, filename in RUNTIME_FILES.items():
        runtime = _parse_manifest(root / filename)
        item = catalog[extension_id]

        if runtime["id"] != extension_id:
            raise RuntimeContractError(
                f"{extension_id}: Hiraukan manifest id is {runtime['id']!r}"
            )
        for field in ("name", "version", "auth"):
            if item.get(field) != runtime[field]:
                raise RuntimeContractError(
                    f"{extension_id}: {field} drift: catalog={item.get(field)!r}, "
                    f"hiraukan={runtime[field]!r}"
                )

        capabilities = item.get("capabilities")
        if not isinstance(capabilities, list) or set(capabilities) != runtime["capabilities"]:
            raise RuntimeContractError(
                f"{extension_id}: capability drift: catalog={sorted(capabilities or [])}, "
                f"hiraukan={sorted(runtime['capabilities'])}"
            )
        languages = item.get("languages")
        if not isinstance(languages, list) or languages != runtime["languages"]:
            raise RuntimeContractError(
                f"{extension_id}: language drift: catalog={languages!r}, "
                f"hiraukan={runtime['languages']!r}"
            )

        delivery = item.get("delivery")
        if not isinstance(delivery, dict) or delivery.get("kind") != "builtin":
            raise RuntimeContractError(f"{extension_id}: only builtin delivery is allowed")
        if delivery.get("runtimeId") != extension_id:
            raise RuntimeContractError(f"{extension_id}: runtimeId must equal extension id")
        checked.append(extension_id)

    return {"runtimeCount": len(checked), "runtimeIds": sorted(checked)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--hiraukan-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.catalog, args.hiraukan_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
