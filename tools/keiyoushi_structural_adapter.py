#!/usr/bin/env python3
"""Deterministic structural adapters from Keiyoushi semantics to Miyorare's UMA/Tsuki runtime.

This is deliberately fail-closed. A structural profile is applied only when:
- the registered canonical source or a runtime it actually uses changed upstream,
- the candidate matches a known upstream generation/signature, and
- the UMA target still matches either the known pre-adaptation form or a proven runtime-equivalent form.

The adapter never copies KeiSource Kotlin into UMA. It translates known semantic changes into the
native Tsuki implementation and records provenance in the existing semantic-adapter report.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

PROVENANCE_FILE = "miyorare-semantic-adapter.json"
PROFILE_CAPABILITY = "structural-profile"
KOMIKU_CANONICAL = "miyorare:miyorare-id:KOMIKU"
KOMIKU_PROFILE = "komiku-keisource-1.6"
KIRYUU_CANONICAL = "miyorare:miyorare-id:KIRYUU"
KIRYUU_PROFILE = "natsuid-alt-title-1.6"
NATSUID_ROOT = "lib-multisrc/natsuid"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=120,
    )


def changed_paths(repo: Path, base: str, candidate: str, path: str) -> list[str]:
    if not base or not candidate or base == candidate:
        return []
    out = git(repo, "diff", "--name-only", f"{base}..{candidate}", "--", path)
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def module_changed(repo: Path, base: str, candidate: str, module: str) -> bool:
    return bool(changed_paths(repo, base, candidate, module))


def alias_by_canonical(manifest: dict[str, Any], canonical: str) -> dict[str, Any] | None:
    for item in manifest.get("aliases", []):
        if isinstance(item, dict) and item.get("canonicalId") == canonical:
            return item
    return None


def replace_known(text: str, old: str, new: str, label: str, changes: list[dict[str, Any]]) -> str:
    if new in text:
        changes.append({
            "changeClass": PROFILE_CAPABILITY,
            "profile": KOMIKU_PROFILE,
            "rule": label,
            "mode": "already-compatible",
        })
        return text
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one known baseline occurrence, found {count}")
    changes.append({
        "changeClass": PROFILE_CAPABILITY,
        "profile": KOMIKU_PROFILE,
        "rule": label,
        "mode": "deterministic-rewrite",
    })
    return text.replace(old, new, 1)


def adapt_komiku(alias: dict[str, Any], keiyoushi_root: Path, uma_root: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    kei = alias.get("keiyoushi") or {}
    uma = alias.get("uma") or {}
    module = kei.get("module")
    uma_file = uma.get("file")
    if not isinstance(module, str) or not isinstance(uma_file, str):
        return None, {"canonicalId": KOMIKU_CANONICAL, "reason": "profile-metadata-missing"}

    build = keiyoushi_root / module / "build.gradle.kts"
    source_files = sorted((keiyoushi_root / module).rglob("Komiku.kt"))
    target = uma_root / uma_file
    if not build.is_file() or len(source_files) != 1 or not target.is_file():
        return None, {
            "canonicalId": KOMIKU_CANONICAL,
            "module": module,
            "umaFile": uma_file,
            "reason": "profile-input-missing",
        }

    build_text = build.read_text(encoding="utf-8")
    kei_text = source_files[0].read_text(encoding="utf-8")
    required_signatures = (
        'libVersion = "1.6"',
        "abstract class Komiku : KeiSource()",
        "override suspend fun getPopularManga",
        '"$apiUrl/other/hot/"',
        "override suspend fun fetchMangaUpdate",
        'filterNot { it.attr("src").contains("komiku-promosi") }',
    )
    missing = [signature for signature in required_signatures if signature not in build_text and signature not in kei_text]
    if missing:
        return None, {
            "canonicalId": KOMIKU_CANONICAL,
            "module": module,
            "umaFile": uma_file,
            "reason": "unknown-komiku-upstream-generation",
            "missingSignatures": missing,
        }

    original = target.read_text(encoding="utf-8")
    text = original
    changes: list[dict[str, Any]] = []

    rules = [
        (
            'override val selectMangaListTitle = "div.kan h3"',
            'override val selectMangaListTitle = "div.kan h3, h3"',
            "broaden-list-title-selector",
        ),
        (
            'override val detailsDescriptionSelector = "#Sinopsis > p"',
            'override val detailsDescriptionSelector = "#Sinopsis > p, p.desc[itemprop=description]"',
            "broaden-description-selector",
        ),
        (
            '''            } else {\n                append("/manga/page/")\n                append(page)\n                append("/")\n                val params = mutableListOf<String>()''',
            '''            } else if (\n                order == SortOrder.POPULARITY &&\n                filter.tags.isEmpty() &&\n                filter.types.isEmpty() &&\n                filter.states.isEmpty()\n            ) {\n                append("/other/hot/")\n                if (page > 1) {\n                    append("page/")\n                    append(page)\n                    append("/")\n                }\n            } else {\n                append("/manga/page/")\n                append(page)\n                append("/")\n                val params = mutableListOf<String>()''',
            "popular-hot-endpoint",
        ),
        (
            'val author = docs.selectFirst("table.inftable tr:has(td:contains(Pengarang)) td:last-child")?.text()',
            'val author = docs.selectFirst("table.inftable tr:has(td:contains(Pengarang)) td:last-child, table.inftable tr:has(td:contains(Komikus)) td:last-child, table.inftable tr:has(td:contains(Author)) td:last-child")?.text()',
            "broaden-author-selector",
        ),
        (
            'val altTitle = docs.selectFirst("table.inftable tr:has(td:contains(Judul Indonesia)) td:last-child")?.text()',
            'val altTitle = docs.selectFirst("table.inftable tr:has(td:contains(Judul Indonesia)) td:last-child, table.inftable tr:has(td:contains(Judul Alternatif)) td:last-child")?.text()',
            "broaden-alternate-title-selector",
        ),
        (
            'val thumbnail = docs.selectFirst("div.ims > img")?.let { img ->',
            'val thumbnail = docs.selectFirst("div.ims > img, img[itemprop=image]")?.let { img ->',
            "broaden-thumbnail-selector",
        ),
        (
            'val trimmedDate = date.substringBefore(" lalu").removeSuffix("s").split(" ")',
            'val trimmedDate = date.substringBefore(" lalu").trim().split(" ")\n        if (trimmedDate.size < 2) return 0L\n        val amount = trimmedDate[0].toIntOrNull() ?: return 0L',
            "safe-relative-date-input",
        ),
        (
            '''        when (trimmedDate[1]) {\n            "jam" -> calendar.add(Calendar.HOUR_OF_DAY, -trimmedDate[0].toInt())\n            "menit" -> calendar.add(Calendar.MINUTE, -trimmedDate[0].toInt())\n            "detik" -> calendar.add(Calendar.SECOND, 0)\n        }''',
            '''        when (trimmedDate[1]) {\n            "detik" -> calendar.add(Calendar.SECOND, -amount)\n            "menit" -> calendar.add(Calendar.MINUTE, -amount)\n            "jam" -> calendar.add(Calendar.HOUR_OF_DAY, -amount)\n            "hari" -> calendar.add(Calendar.DAY_OF_YEAR, -amount)\n            "minggu" -> calendar.add(Calendar.WEEK_OF_YEAR, -amount)\n            "bulan" -> calendar.add(Calendar.MONTH, -amount)\n            "tahun" -> calendar.add(Calendar.YEAR, -amount)\n        }''',
            "extended-relative-date-units",
        ),
        (
            'return doc.select(selectPage).mapIndexed { _, img ->',
            'return doc.select(selectPage)\n            .filterNot { it.attr("src").contains("komiku-promosi") }\n            .mapIndexed { _, img ->',
            "filter-promotional-reader-images",
        ),
    ]

    try:
        for old, new, label in rules:
            text = replace_known(text, old, new, label, changes)
    except ValueError as exc:
        return None, {
            "canonicalId": KOMIKU_CANONICAL,
            "module": module,
            "umaFile": uma_file,
            "reason": "uma-baseline-diverged",
            "detail": str(exc),
        }

    required_output = (
        'append("/other/hot/")',
        'p.desc[itemprop=description]',
        'td:contains(Komikus)',
        'td:contains(Judul Alternatif)',
        'img[itemprop=image]',
        'Calendar.WEEK_OF_YEAR',
        'contains("komiku-promosi")',
    )
    missing_output = [marker for marker in required_output if marker not in text]
    if missing_output:
        return None, {
            "canonicalId": KOMIKU_CANONICAL,
            "module": module,
            "umaFile": uma_file,
            "reason": "adapted-output-verification-failed",
            "missingMarkers": missing_output,
        }

    if text != original:
        target.write_text(text, encoding="utf-8")

    return {
        "canonicalId": KOMIKU_CANONICAL,
        "module": module,
        "umaFile": uma_file,
        "changeClasses": [PROFILE_CAPABILITY],
        "changes": changes + [
            {
                "changeClass": PROFILE_CAPABILITY,
                "profile": KOMIKU_PROFILE,
                "rule": "keiyoushi-runtime-api-migration",
                "mode": "runtime-equivalent-not-source-copy",
                "note": "KeiSource/libVersion/deeplink API mechanics are translated only where they affect Tsuki source behavior.",
            }
        ],
    }, None


def adapt_kiryuu_natsuid(
    alias: dict[str, Any],
    keiyoushi_root: Path,
    uma_root: Path,
    base: str,
    candidate: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Prove the known NatsuId 1.6 alternative-title update is already covered by Tsuki."""
    kei = alias.get("keiyoushi") or {}
    uma = alias.get("uma") or {}
    module = kei.get("module")
    uma_file = uma.get("file")
    if not isinstance(module, str) or not isinstance(uma_file, str):
        return None, {"canonicalId": KIRYUU_CANONICAL, "reason": "profile-metadata-missing"}

    natsu_changes = changed_paths(keiyoushi_root, base, candidate, NATSUID_ROOT)
    expected_changes = {
        f"{NATSUID_ROOT}/build.gradle.kts",
        f"{NATSUID_ROOT}/src/eu/kanade/tachiyomi/multisrc/natsuid/Dto.kt",
    }
    if set(natsu_changes) != expected_changes:
        return None, {
            "canonicalId": KIRYUU_CANONICAL,
            "module": module,
            "reason": "unknown-natsuid-runtime-generation",
            "changedFiles": natsu_changes,
        }

    dto = keiyoushi_root / NATSUID_ROOT / "src/eu/kanade/tachiyomi/multisrc/natsuid/Dto.kt"
    runtime_build = keiyoushi_root / NATSUID_ROOT / "build.gradle.kts"
    kiryuu_sources = sorted((keiyoushi_root / module).rglob("Kiryuu.kt"))
    uma_source = uma_root / uma_file
    natsu_parser = uma_root / "src/main/kotlin/tsuki/parsers/NatsuParser.kt"
    if not dto.is_file() or not runtime_build.is_file() or len(kiryuu_sources) != 1 or not uma_source.is_file() or not natsu_parser.is_file():
        return None, {
            "canonicalId": KIRYUU_CANONICAL,
            "module": module,
            "umaFile": uma_file,
            "reason": "profile-input-missing",
        }

    dto_text = dto.read_text(encoding="utf-8")
    runtime_build_text = runtime_build.read_text(encoding="utf-8")
    kiryuu_text = kiryuu_sources[0].read_text(encoding="utf-8")
    uma_source_text = uma_source.read_text(encoding="utf-8")
    natsu_text = natsu_parser.read_text(encoding="utf-8")

    upstream_signatures = (
        '@JsonNames("metadata")',
        'val meta: MangaMeta? = null',
        '@SerialName("alternative_title")',
        'append("Alternative Names:\\n")',
        'baseVersionCode = 6',
        'libVersion = "1.6"',
        'abstract class Kiryuu : NatsuId()',
        'setQueryParameter("page", "1")',
    )
    combined_upstream = "\n".join((dto_text, runtime_build_text, kiryuu_text))
    missing_upstream = [marker for marker in upstream_signatures if marker not in combined_upstream]
    if missing_upstream:
        return None, {
            "canonicalId": KIRYUU_CANONICAL,
            "module": module,
            "reason": "unknown-natsuid-alt-title-signature",
            "missingSignatures": missing_upstream,
        }

    runtime_equivalence = (
        'NatsuParser(context, MangaParserSource.KIRYUU, "v7.kiryuu.to")',
        'private suspend fun fetchAltTitlesFromPage(pageUrl: String): Set<String>',
        "val altTitles = fetchAltTitlesFromPage",
        "altTitles = altTitles",
    )
    combined_uma = "\n".join((uma_source_text, natsu_text))
    missing_runtime = [marker for marker in runtime_equivalence if marker not in combined_uma]
    if missing_runtime:
        return None, {
            "canonicalId": KIRYUU_CANONICAL,
            "module": module,
            "umaFile": uma_file,
            "reason": "natsuid-runtime-equivalence-not-proven",
            "missingMarkers": missing_runtime,
        }

    return {
        "canonicalId": KIRYUU_CANONICAL,
        "module": module,
        "umaFile": uma_file,
        "changeClasses": [PROFILE_CAPABILITY],
        "changes": [
            {
                "changeClass": PROFILE_CAPABILITY,
                "profile": KIRYUU_PROFILE,
                "rule": "natsuid-alternative-title-metadata",
                "mode": "already-compatible-runtime-equivalent",
                "note": "Keiyoushi now reads alternative_title from REST metadata; Tsuki NatsuParser already resolves alternate titles from the manga page and stores them in Manga.altTitles.",
            },
            {
                "changeClass": PROFILE_CAPABILITY,
                "profile": KIRYUU_PROFILE,
                "rule": "natsuid-version-bump",
                "mode": "metadata-only-after-runtime-equivalence",
                "note": "NatsuId baseVersionCode changed 5 -> 6; no additional runtime source file changed beyond the recognized DTO behavior.",
            },
        ],
    }, None


def merge_applied(report: dict[str, Any], item: dict[str, Any]) -> None:
    applied = report.setdefault("applied", [])
    for existing in applied:
        if not isinstance(existing, dict) or existing.get("canonicalId") != item["canonicalId"]:
            continue
        existing_classes = {value for value in existing.get("changeClasses", []) if isinstance(value, str)}
        existing_classes.update(item.get("changeClasses", []))
        existing["changeClasses"] = sorted(existing_classes)
        existing.setdefault("changes", []).extend(item.get("changes", []))
        return
    applied.append(item)


def clear_blocked(report: dict[str, Any], canonical: str) -> None:
    report["blocked"] = [
        item for item in report.get("blocked", [])
        if not isinstance(item, dict) or item.get("canonicalId") != canonical
    ]


def apply_structural_adapters(
    aliases_path: Path,
    keiyoushi_root: Path,
    uma_root: Path,
    output: Path,
) -> dict[str, Any]:
    manifest = load_json(aliases_path)
    report = load_json(output) if output.is_file() else {
        "schema": 2,
        "adapter": "keiyoushi-semantic",
        "capabilities": [],
        "base": None,
        "candidate": None,
        "applied": [],
        "appliedCanonicalIds": [],
        "unchangedCanonicalIds": [],
        "blocked": [],
        "state": "clear",
    }

    capabilities = {value for value in report.get("capabilities", []) if isinstance(value, str)}
    capabilities.add(PROFILE_CAPABILITY)
    report["capabilities"] = sorted(capabilities)
    base = report.get("base")
    candidate = report.get("candidate")

    if isinstance(base, str) and isinstance(candidate, str):
        komiku_alias = alias_by_canonical(manifest, KOMIKU_CANONICAL)
        if komiku_alias:
            module = (komiku_alias.get("keiyoushi") or {}).get("module")
            if isinstance(module, str) and module_changed(keiyoushi_root, base, candidate, module):
                applied, blocked = adapt_komiku(komiku_alias, keiyoushi_root, uma_root)
                if applied:
                    merge_applied(report, applied)
                    clear_blocked(report, KOMIKU_CANONICAL)
                elif blocked:
                    clear_blocked(report, KOMIKU_CANONICAL)
                    report.setdefault("blocked", []).append(blocked)

        kiryuu_alias = alias_by_canonical(manifest, KIRYUU_CANONICAL)
        if kiryuu_alias and changed_paths(keiyoushi_root, base, candidate, NATSUID_ROOT):
            applied, blocked = adapt_kiryuu_natsuid(
                kiryuu_alias,
                keiyoushi_root,
                uma_root,
                base,
                candidate,
            )
            if applied:
                merge_applied(report, applied)
                clear_blocked(report, KIRYUU_CANONICAL)
            elif blocked:
                clear_blocked(report, KIRYUU_CANONICAL)
                report.setdefault("blocked", []).append(blocked)

    report["appliedCanonicalIds"] = sorted({
        item.get("canonicalId") for item in report.get("applied", [])
        if isinstance(item, dict) and isinstance(item.get("canonicalId"), str)
    })
    report["state"] = "blocked" if report.get("blocked") else "clear"
    report["structuralProfiles"] = [KOMIKU_PROFILE, KIRYUU_PROFILE]

    save_json(output, report)
    save_json(uma_root / PROVENANCE_FILE, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aliases", type=Path, required=True)
    parser.add_argument("--keiyoushi-root", type=Path, required=True)
    parser.add_argument("--uma-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = apply_structural_adapters(
        args.aliases.resolve(),
        args.keiyoushi_root.resolve(),
        args.uma_root.resolve(),
        args.output.resolve(),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict and report.get("state") == "blocked":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
