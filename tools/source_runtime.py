#!/usr/bin/env python3
"""Per-source runtime probes and recovery planning for Miyorare Source Packs.

This module deliberately separates source health from provider promotion. A single
broken source can be quarantined/recovered without declaring every source in its
provider broken. Network probes are conservative: an HTTP response below 500
counts as reachable, while hard failures must repeat before a source is BROKEN.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, NoReturn

HEX40 = re.compile(r"^[0-9a-f]{40}$")
ANNOTATION_RE = re.compile(
    r'@MangaSourceParser\(\s*"([^"]+)"\s*,\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?'
)
URL_RE = re.compile(r'https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\d+)?')
HOST_LITERAL_RE = re.compile(r'"([A-Za-z0-9.-]+\.[A-Za-z]{2,})"')
BASE_URL_RE = re.compile(r'\bbaseUrl\s*=\s*"https?://([^"/]+)')
PROVIDERS = ("keiyoushi", "uma", "gekkoushi")
HEALTH = {"HEALTHY", "DEGRADED", "BROKEN", "UNKNOWN"}
RECOVERY_ACTIONS = {
    "NONE",
    "REPROBE",
    "ADAPT_LATEST",
    "REFRESH_UPSTREAM",
    "TRY_PREVIOUS_HEALTHY",
    "TRY_CANONICAL_FALLBACK",
    "TEMPORARILY_UNAVAILABLE",
}
DEFAULT_FAIL_THRESHOLD = 3


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


def unique_commits(values: list[Any], limit: int = 5) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and HEX40.fullmatch(value) and value not in result:
            result.append(value)
    return result[:limit]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def parser_blocks(text: str) -> list[tuple[str, str, str, str]]:
    matches = list(ANNOTATION_RE.finditer(text))
    result: list[tuple[str, str, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result.append(
            (
                match.group(1),
                match.group(2),
                match.group(3) or "",
                text[match.start():end],
            )
        )
    return result


def parser_annotation(text: str) -> tuple[str, str, str] | None:
    blocks = parser_blocks(text)
    if not blocks:
        return None
    sid, name, lang, _ = blocks[0]
    return sid, name, lang


def first_host(text: str) -> str | None:
    match = BASE_URL_RE.search(text)
    if match:
        return match.group(1).lower().rstrip(".")
    match = URL_RE.search(text)
    if match:
        return match.group(1).lower().rstrip(".")
    for match in HOST_LITERAL_RE.finditer(text):
        host = match.group(1).lower().rstrip(".")
        if "." in host and not host.endswith((".kt", ".json", ".xml")):
            return host
    return None


def alias_maps(aliases: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_uma_file: dict[str, dict[str, Any]] = {}
    by_keiyoushi_module: dict[str, dict[str, Any]] = {}
    for item in aliases.get("aliases", []):
        if not isinstance(item, dict):
            continue
        uma = item.get("uma")
        kei = item.get("keiyoushi")
        if isinstance(uma, dict) and isinstance(uma.get("file"), str):
            by_uma_file[uma["file"]] = item
        if isinstance(kei, dict) and isinstance(kei.get("module"), str):
            by_keiyoushi_module[kei["module"]] = item
    return by_uma_file, by_keiyoushi_module


def source_key(provider: str, pack: str, source_id: str) -> str:
    return f"{provider}:{pack}:{source_id}"


def source_entry(
    provider: str,
    pack: str,
    source_id: str,
    name: str,
    path: str,
    host: str | None,
    canonical_id: str | None = None,
) -> dict[str, Any]:
    return {
        "sourceKey": source_key(provider, pack, source_id),
        "provider": provider,
        "pack": pack,
        "sourceId": source_id,
        "sourceName": name,
        "path": path,
        "canonicalId": canonical_id,
        "probeHost": host,
    }


def discover_keiyoushi(aliases: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in aliases.get("aliases", []):
        if not isinstance(item, dict):
            continue
        official = item.get("official")
        kei = item.get("keiyoushi")
        if not isinstance(official, dict) or not isinstance(kei, dict):
            continue
        module = kei.get("module")
        if not isinstance(module, str):
            continue
        source_name = str(official.get("sourceName") or kei.get("sourceName") or Path(module).name)
        pack = str(official.get("pack") or item.get("language") or "unknown")
        verified = item.get("verifiedDomain")
        text = read_text(root / module / "build.gradle.kts")
        host = str(verified).lower() if isinstance(verified, str) and verified else first_host(text)
        result.append(
            source_entry(
                "keiyoushi",
                pack,
                source_name.upper(),
                source_name,
                module,
                host,
                item.get("canonicalId") if isinstance(item.get("canonicalId"), str) else None,
            )
        )
    return result


def discover_uma(packs: dict[str, Any], aliases: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    by_uma_file, _ = alias_maps(aliases)
    result: list[dict[str, Any]] = []
    for pack in ("id", "en"):
        pack_cfg = packs.get("packs", {}).get(pack, {})
        for rel in pack_cfg.get("sources", []):
            if not isinstance(rel, str):
                continue
            upstream_rel = f"src/main/kotlin/tsuki/site/{pack}/{rel}"
            text = read_text(root / upstream_rel)
            annotation = parser_annotation(text)
            sid = annotation[0] if annotation else Path(rel).stem.upper()
            name = annotation[1] if annotation else Path(rel).stem
            alias = by_uma_file.get(upstream_rel)
            canonical = alias.get("canonicalId") if isinstance(alias, dict) else None
            verified = alias.get("verifiedDomain") if isinstance(alias, dict) else None
            host = str(verified).lower() if isinstance(verified, str) and verified else first_host(text)
            result.append(source_entry("uma", pack, sid, name, upstream_rel, host, canonical))
    return result


def discover_gekkoushi(packs: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    global_ids = {
        str(item)
        for item in packs.get("packs", {}).get("global", {}).get("gekkoushiSources", [])
        if isinstance(item, str)
    }
    for lang, pack in (("id", "id"), ("en", "en"), ("all", "global")):
        base = root / "src/main/kotlin/tsuki/site" / lang
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.kt")):
            text = read_text(path)
            rel = path.relative_to(root).as_posix()
            for sid, name, _, block in parser_blocks(text):
                if pack == "global" and global_ids and sid not in global_ids:
                    continue
                result.append(source_entry("gekkoushi", pack, sid, name, rel, first_host(block), None))
    return result


def discover_inventory(
    packs_path: Path,
    aliases_path: Path,
    uma_root: Path,
    gekkoushi_root: Path,
    keiyoushi_root: Path,
) -> list[dict[str, Any]]:
    packs = load_json(packs_path)
    aliases = load_json(aliases_path)
    items = [
        *discover_keiyoushi(aliases, keiyoushi_root),
        *discover_uma(packs, aliases, uma_root),
        *discover_gekkoushi(packs, gekkoushi_root),
    ]
    dedup: dict[str, dict[str, Any]] = {}
    for item in items:
        dedup[item["sourceKey"]] = item
    return [dedup[key] for key in sorted(dedup)]


def http_probe(host: str, timeout: float = 8.0) -> dict[str, Any]:
    url = f"https://{host}/"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Miyorare-Source-Health/1.0 (+https://github.com/Noirero/Miyorare-Source-Packs)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            response.read(1024)
            return {"reachable": status < 500, "httpStatus": status, "url": url}
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        return {
            "reachable": status < 500,
            "httpStatus": status,
            "url": url,
            "detail": f"http-{status}",
        }
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return {"reachable": False, "url": url, "detail": type(exc).__name__}


def active_commit(status: dict[str, Any], provider: str) -> str | None:
    entry = status.get("providers", {}).get(provider, {})
    value = entry.get("activeCommit") or entry.get("lastKnownGood")
    return value if isinstance(value, str) and HEX40.fullmatch(value) else None


def initialize_source_state(
    inventory: list[dict[str, Any]],
    raw_state: dict[str, Any],
    status: dict[str, Any],
) -> dict[str, Any]:
    previous = raw_state.get("sources", {}) if isinstance(raw_state, dict) else {}
    out: dict[str, Any] = {"schema": 1, "sources": {}}
    for item in inventory:
        key = item["sourceKey"]
        old = previous.get(key) if isinstance(previous, dict) else None
        old = old if isinstance(old, dict) else {}
        commit = active_commit(status, item["provider"])
        entry = dict(old)
        entry.update(item)
        entry["activeCommit"] = commit
        if old.get("activeCommit") != commit:
            entry["runtimeHealth"] = "UNKNOWN"
            entry["consecutiveFailures"] = 0
            entry["recoveryState"] = "IDLE"
        else:
            health = str(old.get("runtimeHealth", "UNKNOWN")).upper()
            entry["runtimeHealth"] = health if health in HEALTH else "UNKNOWN"
            entry["consecutiveFailures"] = max(0, int(old.get("consecutiveFailures", 0) or 0))
            entry["recoveryState"] = str(old.get("recoveryState", "IDLE"))
        entry["healthyHistory"] = unique_commits(
            [*old.get("healthyHistory", []), commit] if commit else list(old.get("healthyHistory", []))
        )
        out["sources"][key] = entry
    return out


def apply_probe_result(entry: dict[str, Any], result: dict[str, Any], fail_threshold: int) -> None:
    if result.get("skipped"):
        entry["probeOutcome"] = "no-probe-target"
        return
    entry["lastProbe"] = {k: v for k, v in result.items() if k != "reachable"}
    if result.get("reachable") is True:
        entry["runtimeHealth"] = "HEALTHY"
        entry["consecutiveFailures"] = 0
        entry["recoveryState"] = "IDLE"
        commit = entry.get("activeCommit")
        entry["healthyHistory"] = unique_commits([commit, *entry.get("healthyHistory", [])])
        entry["probeOutcome"] = "reachable"
    else:
        failures = int(entry.get("consecutiveFailures", 0)) + 1
        entry["consecutiveFailures"] = failures
        entry["runtimeHealth"] = "BROKEN" if failures >= fail_threshold else "DEGRADED"
        entry["recoveryState"] = "ADAPTING_LATEST" if entry["runtimeHealth"] == "BROKEN" else "IDLE"
        entry["probeOutcome"] = "hard-failure"


def probe_inventory(
    inventory: list[dict[str, Any]],
    state: dict[str, Any],
    timeout: float,
    workers: int,
    fail_threshold: int,
) -> dict[str, Any]:
    by_key = state["sources"]
    targets = [(item["sourceKey"], item.get("probeHost")) for item in inventory]
    results: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(http_probe, host, timeout): key
            for key, host in targets
            if isinstance(host, str) and host
        }
        for key, host in targets:
            if not isinstance(host, str) or not host:
                results[key] = {"skipped": True, "detail": "no-probe-host"}
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = {"reachable": False, "detail": type(exc).__name__}
    for key, result in results.items():
        apply_probe_result(by_key[key], result, fail_threshold)
    return results


def provider_summary(state: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for provider in PROVIDERS:
        entries = [e for e in state["sources"].values() if e.get("provider") == provider]
        counts = {health: 0 for health in HEALTH}
        for entry in entries:
            health = entry.get("runtimeHealth", "UNKNOWN")
            counts[health if health in HEALTH else "UNKNOWN"] += 1
        probed = len(entries) - counts["UNKNOWN"]
        if probed == 0:
            aggregate = "UNKNOWN"
        elif counts["BROKEN"] == probed:
            aggregate = "BROKEN"
        elif counts["BROKEN"] or counts["DEGRADED"]:
            aggregate = "DEGRADED"
        elif counts["HEALTHY"] == probed:
            aggregate = "HEALTHY"
        else:
            aggregate = "UNKNOWN"
        summary[provider] = {"runtimeHealth": aggregate, "counts": counts, "sourceCount": len(entries)}
    return {"schema": 1, "providers": summary}


def canonical_fallbacks(state: dict[str, Any], source: dict[str, Any]) -> list[dict[str, str]]:
    canonical = source.get("canonicalId")
    if not isinstance(canonical, str) or not canonical:
        return []
    result = []
    for other in state["sources"].values():
        if other.get("sourceKey") == source.get("sourceKey"):
            continue
        if other.get("canonicalId") != canonical:
            continue
        if other.get("runtimeHealth") != "HEALTHY":
            continue
        result.append({"sourceKey": other["sourceKey"], "provider": other["provider"]})
    return result


def recovery_attempts(source: dict[str, Any], status: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    health = source.get("runtimeHealth")
    if health == "HEALTHY" or health == "UNKNOWN":
        return [{"action": "NONE"}]
    if health == "DEGRADED":
        return [{"action": "REPROBE"}]

    provider = source["provider"]
    provider_status = status.get("providers", {}).get(provider, {})
    active = source.get("activeCommit")
    candidate = provider_status.get("candidate")
    attempts: list[dict[str, Any]] = []
    if isinstance(candidate, str) and HEX40.fullmatch(candidate) and candidate != active:
        attempts.append({"action": "ADAPT_LATEST", "commit": candidate})
    else:
        attempts.append({"action": "REFRESH_UPSTREAM"})

    for commit in unique_commits(source.get("healthyHistory", [])):
        if commit != active:
            attempts.append({"action": "TRY_PREVIOUS_HEALTHY", "commit": commit})
            break

    fallbacks = canonical_fallbacks(state, source)
    if fallbacks:
        attempts.append({"action": "TRY_CANONICAL_FALLBACK", "target": fallbacks[0]})
    attempts.append({"action": "TEMPORARILY_UNAVAILABLE"})
    return attempts


def build_recovery_queue(state: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    queue: list[dict[str, Any]] = []
    for source in state["sources"].values():
        if source.get("runtimeHealth") not in {"DEGRADED", "BROKEN"}:
            continue
        attempts = recovery_attempts(source, status, state)
        selected = attempts[0]
        token_basis = selected.get("commit") or selected.get("action")
        token = f"{source['sourceKey']}|{selected['action']}|{token_basis}|{source.get('activeCommit')}"
        dispatch_needed = (
            selected["action"] in {"ADAPT_LATEST", "REFRESH_UPSTREAM"}
            and source.get("lastRecoveryDispatchToken") != token
        )
        queue.append(
            {
                "sourceKey": source["sourceKey"],
                "provider": source["provider"],
                "canonicalId": source.get("canonicalId"),
                "runtimeHealth": source["runtimeHealth"],
                "attempts": attempts,
                "selectedAction": selected["action"],
                "dispatchToken": token,
                "dispatchNeeded": dispatch_needed,
            }
        )
    return {"schema": 1, "queue": queue}


def acknowledge_dispatch(state: dict[str, Any], queue: dict[str, Any]) -> None:
    for item in queue.get("queue", []):
        if item.get("dispatchNeeded") is not True:
            continue
        source = state["sources"].get(item.get("sourceKey"))
        if isinstance(source, dict):
            source["lastRecoveryDispatchToken"] = item.get("dispatchToken")


def validate_state(state: dict[str, Any], queue: dict[str, Any] | None = None) -> None:
    if state.get("schema") != 1 or not isinstance(state.get("sources"), dict):
        fail("invalid source health schema")
    for key, entry in state["sources"].items():
        if entry.get("sourceKey") != key:
            fail(f"source key mismatch: {key}")
        if entry.get("provider") not in PROVIDERS:
            fail(f"unsupported provider for {key}")
        if entry.get("runtimeHealth") not in HEALTH:
            fail(f"invalid runtime health for {key}")
        commit = entry.get("activeCommit")
        if commit is not None and (not isinstance(commit, str) or not HEX40.fullmatch(commit)):
            fail(f"invalid active commit for {key}")
    if queue is not None:
        for item in queue.get("queue", []):
            if item.get("selectedAction") not in RECOVERY_ACTIONS:
                fail(f"invalid recovery action for {item.get('sourceKey')}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe")
    p_probe.add_argument("--packs", type=Path, required=True)
    p_probe.add_argument("--aliases", type=Path, required=True)
    p_probe.add_argument("--uma-root", type=Path, required=True)
    p_probe.add_argument("--gekkoushi-root", type=Path, required=True)
    p_probe.add_argument("--keiyoushi-root", type=Path, required=True)
    p_probe.add_argument("--status", type=Path, required=True)
    p_probe.add_argument("--source-health", type=Path, required=True)
    p_probe.add_argument("--probe-output", type=Path, required=True)
    p_probe.add_argument("--provider-summary", type=Path, required=True)
    p_probe.add_argument("--recovery-queue", type=Path, required=True)
    p_probe.add_argument("--timeout", type=float, default=8.0)
    p_probe.add_argument("--workers", type=int, default=12)
    p_probe.add_argument("--fail-threshold", type=int, default=DEFAULT_FAIL_THRESHOLD)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--source-health", type=Path, required=True)
    p_validate.add_argument("--recovery-queue", type=Path)

    p_ack = sub.add_parser("acknowledge-dispatch")
    p_ack.add_argument("--source-health", type=Path, required=True)
    p_ack.add_argument("--recovery-queue", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "probe":
        status = load_json(args.status.resolve())
        inventory = discover_inventory(
            args.packs.resolve(),
            args.aliases.resolve(),
            args.uma_root.resolve(),
            args.gekkoushi_root.resolve(),
            args.keiyoushi_root.resolve(),
        )
        raw_state = load_json(args.source_health.resolve()) if args.source_health.is_file() else {"schema": 1, "sources": {}}
        state = initialize_source_state(inventory, raw_state, status)
        results = probe_inventory(inventory, state, args.timeout, args.workers, max(1, args.fail_threshold))
        queue = build_recovery_queue(state, status)
        validate_state(state, queue)
        save_json(args.source_health.resolve(), state)
        save_json(args.probe_output.resolve(), {"schema": 1, "results": results})
        save_json(args.provider_summary.resolve(), provider_summary(state))
        save_json(args.recovery_queue.resolve(), queue)
        print(json.dumps(provider_summary(state), indent=2))
    elif args.command == "validate":
        state = load_json(args.source_health.resolve())
        queue = load_json(args.recovery_queue.resolve()) if args.recovery_queue and args.recovery_queue.is_file() else None
        validate_state(state, queue)
        print("per-source runtime state is valid")
    elif args.command == "acknowledge-dispatch":
        state = load_json(args.source_health.resolve())
        queue = load_json(args.recovery_queue.resolve())
        acknowledge_dispatch(state, queue)
        validate_state(state, queue)
        save_json(args.source_health.resolve(), state)
    else:
        fail(f"unsupported command {args.command}")


if __name__ == "__main__":
    main()
