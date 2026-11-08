#!/usr/bin/env python3
"""Offline validation for the pinned EN/ID official LNReader candidate inventory.

This file is *not* an install manifest. Only signed Source Pack release assets with
SHA-256 binding may transition individual candidates into an installable state.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_STATES = {"INVENTORIED", "TESTING", "READY", "PROBLEM"}
ALLOWED_CHECKS = {"UNKNOWN", "PASS", "FAIL"}
ID_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LANGS = {"en": ("English", "/english/"), "id": ("Bahasa Indonesia", "/indonesian/")}

class CandidateRegistryError(ValueError):
    pass

def fail(message: str) -> None:
    raise CandidateRegistryError(message)

def validate(doc: dict) -> dict[str, int]:
    if doc.get("schemaVersion") != 1 or doc.get("kind") != "MIYORARE_LNREADER_NOVEL_CANDIDATES":
        fail("unexpected candidate registry format")
    scope = doc.get("scope", {})
    if scope.get("languages") != ["en", "id"] or scope.get("installPolicy") != "EXPLICIT_USER_ACTION":
        fail("unapproved language or installation policy")
    if scope.get("unverifiedInstallAllowed") is not False:
        fail("unverified plugin installation must remain forbidden")
    upstream = doc.get("upstream", {})
    commit = upstream.get("commit", "")
    if not SHA_RE.fullmatch(commit):
        fail("upstream reference must be an immutable commit")
    if upstream.get("repository") != "LNReader/lnreader-plugins" or upstream.get("branch") != "plugins/v3.0.0":
        fail("unexpected upstream owner/branch")
    if upstream.get("indexPath") != ".dist/plugins.min.json" or upstream.get("indexUrl") != (
        f"https://raw.githubusercontent.com/LNReader/lnreader-plugins/{commit}/.dist/plugins.min.json"
    ):
        fail("upstream index provenance mismatch")
    candidates = doc.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        fail("empty candidate list")
    seen = set()
    counts = {"en": 0, "id": 0}
    for item in candidates:
        if not isinstance(item, dict):
            fail("candidate must be an object")
        ident = item.get("id")
        if not isinstance(ident, str) or not ID_RE.fullmatch(ident) or ident in seen:
            fail("duplicate or invalid immutable LNReader plugin ID")
        seen.add(ident)
        lang = item.get("language")
        if lang not in LANGS:
            fail(f"{ident}: non-EN/ID language")
        counts[lang] += 1
        label, code_dir = LANGS[lang]
        if item.get("upstreamLanguage") != label:
            fail(f"{ident}: upstream language mismatch")
        if not all(isinstance(item.get(field), str) and item[field].strip() for field in ("name", "site", "version", "codeUrl", "iconUrl")):
            fail(f"{ident}: incomplete upstream metadata")
        if not VERSION_RE.fullmatch(item["version"]):
            fail(f"{ident}: invalid plugin version")
        code_url = item["codeUrl"]
        if not code_url.startswith(
            "https://raw.githubusercontent.com/lnreader/lnreader-plugins/plugins/v3.0.0/.js/src/plugins/"
        ) or code_dir not in code_url or not code_url.endswith(".js"):
            fail(f"{ident}: code URL does not belong to official LNReader {lang} catalog")
        if urlparse(item["site"]).scheme != "https":
            fail(f"{ident}: invalid source site origin")
        if not item["iconUrl"].startswith("https://raw.githubusercontent.com/lnreader/lnreader-plugins/"):
            fail(f"{ident}: unexpected icon origin")
        state = item.get("state")
        checks = item.get("checks", {})
        if state not in ALLOWED_STATES or set(checks) != {"catalog", "api", "runtime", "android"}:
            fail(f"{ident}: incomplete state/check metadata")
        if not all(x in ALLOWED_CHECKS for x in checks.values()) or checks["catalog"] != "PASS":
            fail(f"{ident}: unsupported verification status")
        dist = item.get("distribution", {})
        if dist.get("artifact") == "UNPUBLISHED":
            if dist.get("verifiedSha256") is not None or state == "READY":
                fail(f"{ident}: unpublished candidate may not claim install readiness")
        else:
            if dist.get("artifact") != "SEALED" or not SHA256_RE.fullmatch(dist.get("verifiedSha256") or ""):
                fail(f"{ident}: only signed digest-bound artifacts can be installable")
        if state == "READY" and any(checks[k] != "PASS" for k in ("api", "runtime", "android")):
            fail(f"{ident}: READY requires api, runtime, and Android validation")
        if state == "INVENTORIED" and any(checks[k] != "UNKNOWN" for k in ("api", "runtime", "android")):
            fail(f"{ident}: INVENTORIED cannot silently claim further validation")
    pilot = doc.get("pilot", {})
    if pilot.get("pluginId") != "chikari" or "chikari" not in seen or pilot.get("state") != "TESTING":
        fail("Chikari must remain a non-production pilot")
    if pilot.get("evidence", {}).get("api") != "PASS" or pilot.get("evidence", {}).get("android") != "UNKNOWN":
        fail("pilot API evidence may not be confused with Android production readiness")
    chikari = next(item for item in candidates if item["id"] == "chikari")
    if chikari["state"] != "TESTING" or chikari["checks"]["api"] != "PASS":
        fail("pilot registry state does not match actual API validation")
    return counts

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=Path("registry/lnreader/en-id-candidates.v1.json"))
    args = parser.parse_args()
    counts = validate(json.loads(args.registry.read_text(encoding="utf-8")))
    print(f"VALID: {sum(counts.values())} inventory candidates (en={counts['en']}, id={counts['id']}); none implicitly installed")

if __name__ == "__main__":
    main()
