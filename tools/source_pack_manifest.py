#!/usr/bin/env python3
"""Generate and validate the authoritative Miyorare Source Pack release manifest (schema 3)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
REQUIRED_LOGICAL_PACKS = ("miyorare-id", "miyorare-en", "miyorare-global")
REQUIRED_PACK_FILES = ("id", "en", "global")
REQUIRED_UPSTREAMS = ("uma", "gekkoushi", "keiyoushi")


class ManifestError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestError(f"{path} must contain a JSON object")
    return value


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_hex40(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value.lower()):
        raise ManifestError(f"{label} must be a 40-character git SHA")
    return value.lower()


def require_hex64(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value.lower()):
        raise ManifestError(f"{label} must be a SHA-256 digest")
    return value.lower()


def compatibility_snapshot_id(
    contract_sha256: str,
    runtime_commit: str,
    builder_commit: str,
    farm_commit: str,
    upstreams: dict[str, str],
) -> str:
    payload = {
        "schemaVersion": 1,
        "contractSha256": require_hex64(contract_sha256, "compatibilitySnapshot.contractSha256"),
        "runtimeCommit": require_hex40(runtime_commit, "runtimeCompatibility.commit"),
        "builderCommit": require_hex40(builder_commit, "sourceCommit"),
        "farmCommit": require_hex40(farm_commit, "compatibilitySnapshot.farmCommit"),
        "providerCommits": {
            name: require_hex40(upstreams.get(name), f"upstreams.{name}")
            for name in REQUIRED_UPSTREAMS
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b"miyorare-compatibility-snapshot-v1\n" + canonical).hexdigest()


def validate(
    manifest: dict[str, Any],
    contract: dict[str, Any],
    expected_tag: str | None = None,
    expected_contract_sha256: str | None = None,
    require_compatibility_snapshot: bool = False,
) -> None:
    if manifest.get("schema") != contract.get("format", {}).get("releaseManifestSchema"):
        raise ManifestError(f"unsupported release manifest schema: {manifest.get('schema')!r}")
    if manifest.get("schema") != 3:
        raise ManifestError("Phase 2 requires release manifest schema 3")

    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ManifestError("manifest.version must use MAJOR.MINOR.PATCH")
    tag = manifest.get("tag")
    if tag != f"miyorare-sources-v{version}":
        raise ManifestError("manifest tag/version mismatch")
    if expected_tag is not None and tag != expected_tag:
        raise ManifestError("release manifest tag does not match expected GitHub release tag")

    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict):
        raise ManifestError("manifest.compatibility is required")
    contract_compat = contract.get("compatibility") or {}
    if compatibility.get("channel") != contract_compat.get("stableChannel"):
        raise ManifestError("release channel is not the stable contract channel")
    if compatibility.get("compatibilityEpoch") != contract_compat.get("compatibilityEpoch"):
        raise ManifestError("compatibility epoch mismatch")
    if compatibility.get("tsukiApi") != contract_compat.get("tsukiApi"):
        raise ManifestError("Tsuki API mismatch")
    minimum = compatibility.get("minMiyorareVersionCode")
    maximum = compatibility.get("maxMiyorareVersionCode")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
        raise ManifestError("minMiyorareVersionCode must be a positive integer")
    if maximum is not None and (
        not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < minimum
    ):
        raise ManifestError("maxMiyorareVersionCode must be null or >= minMiyorareVersionCode")
    if compatibility.get("releaseLockRequired") is not True:
        raise ManifestError("schema 3 stable release must require the release lock")
    required = compatibility.get("requiredLogicalPacks")
    if not isinstance(required, list) or set(required) != set(REQUIRED_LOGICAL_PACKS) or len(required) != len(REQUIRED_LOGICAL_PACKS):
        raise ManifestError("requiredLogicalPacks must exactly name ID, EN, and Global")

    if manifest.get("sourceRepository") != "Noirero/Miyorare" or manifest.get("sourceBranch") != "beta":
        raise ManifestError("builder source provenance must be Noirero/Miyorare@beta")
    require_hex40(manifest.get("sourceCommit"), "sourceCommit")

    runtime = manifest.get("runtimeCompatibility")
    if not isinstance(runtime, dict):
        raise ManifestError("runtimeCompatibility is required")
    if runtime.get("repository") != "Noirero/Miyorare" or runtime.get("branch") != "main":
        raise ManifestError("stable runtime compatibility baseline must be Noirero/Miyorare@main")
    require_hex40(runtime.get("commit"), "runtimeCompatibility.commit")
    if runtime.get("versionCode") != minimum:
        raise ManifestError("runtimeCompatibility.versionCode must equal minMiyorareVersionCode")
    if runtime.get("tsukiApi") != compatibility.get("tsukiApi"):
        raise ManifestError("runtimeCompatibility.tsukiApi mismatch")

    upstreams = manifest.get("upstreams")
    if not isinstance(upstreams, dict) or set(upstreams) != set(REQUIRED_UPSTREAMS):
        raise ManifestError("upstreams must exactly contain UMA, Gekkoushi, and Keiyoushi pins")
    for name in REQUIRED_UPSTREAMS:
        require_hex40(upstreams.get(name), f"upstreams.{name}")

    snapshot = manifest.get("compatibilitySnapshot")
    snapshot_id_raw = manifest.get("compatibilitySnapshotId")
    if snapshot is None and snapshot_id_raw is None:
        if require_compatibility_snapshot:
            raise ManifestError("compatibilitySnapshotId is required for new stable releases")
    else:
        if not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 1:
            raise ManifestError("compatibilitySnapshot schemaVersion must be 1")
        if snapshot.get("algorithm") != "sha256":
            raise ManifestError("compatibilitySnapshot algorithm must be sha256")
        contract_digest = require_hex64(snapshot.get("contractSha256"), "compatibilitySnapshot.contractSha256")
        farm_commit = require_hex40(snapshot.get("farmCommit"), "compatibilitySnapshot.farmCommit")
        if expected_contract_sha256 is not None and contract_digest != require_hex64(
            expected_contract_sha256, "expected contract SHA-256"
        ):
            raise ManifestError("compatibilitySnapshot contract SHA-256 mismatch")
        snapshot_id = require_hex64(snapshot_id_raw, "compatibilitySnapshotId")
        expected_snapshot_id = compatibility_snapshot_id(
            contract_digest,
            runtime["commit"],
            manifest["sourceCommit"],
            farm_commit,
            upstreams,
        )
        if snapshot_id != expected_snapshot_id:
            raise ManifestError("compatibilitySnapshotId does not match immutable compatibility inputs")

    packs = manifest.get("packs")
    if not isinstance(packs, list) or not packs:
        raise ManifestError("manifest.packs is required")
    by_id: dict[str, dict[str, Any]] = {}
    expected_languages = {"miyorare-id": "id", "miyorare-en": "en", "miyorare-global": "all"}
    for pack in packs:
        if not isinstance(pack, dict):
            raise ManifestError("invalid pack entry")
        plugin_id = pack.get("pluginId")
        if not isinstance(plugin_id, str) or plugin_id in by_id:
            raise ManifestError("pack pluginId is missing or duplicated")
        by_id[plugin_id] = pack
        if pack.get("language") != expected_languages.get(plugin_id):
            raise ManifestError(f"unexpected language for {plugin_id}")
        source_count = pack.get("sourceCount")
        if not isinstance(source_count, int) or isinstance(source_count, bool) or source_count < 1:
            raise ManifestError(f"invalid sourceCount for {plugin_id}")
        shards = pack.get("shards")
        if not isinstance(shards, list) or not shards:
            raise ManifestError(f"{plugin_id} has no shards")
        seen_assets: set[str] = set()
        for shard in shards:
            if not isinstance(shard, dict):
                raise ManifestError(f"{plugin_id} has an invalid shard")
            asset_name = shard.get("assetName")
            digest = shard.get("sha256")
            size = shard.get("size")
            if (
                not isinstance(asset_name, str)
                or not asset_name.endswith(".jar")
                or Path(asset_name).name != asset_name
                or asset_name in seen_assets
            ):
                raise ManifestError(f"{plugin_id} has an invalid or duplicate shard asset")
            seen_assets.add(asset_name)
            if not isinstance(digest, str) or not HEX64.fullmatch(digest.lower()):
                raise ManifestError(f"{asset_name} has an invalid SHA-256")
            if not isinstance(size, int) or isinstance(size, bool) or size < 1 or size > contract["format"]["maxArtifactBytes"]:
                raise ManifestError(f"{asset_name} has an invalid size")
    if set(by_id) != set(REQUIRED_LOGICAL_PACKS):
        raise ManifestError("manifest packs must exactly contain ID, EN, and Global")


def generate(
    dist: Path,
    version: str,
    source_commit: str,
    runtime_commit: str,
    runtime_version_code: int,
    tsuki_api: str,
    compatibility_epoch: int,
    upstreams: dict[str, str],
    farm_commit: str,
    contract_sha256: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    if not SEMVER.fullmatch(version):
        raise ManifestError("version must use MAJOR.MINOR.PATCH")
    require_hex40(source_commit, "sourceCommit")
    require_hex40(runtime_commit, "runtimeCompatibility.commit")
    for name in REQUIRED_UPSTREAMS:
        require_hex40(upstreams.get(name), f"upstreams.{name}")
    require_hex40(farm_commit, "compatibilitySnapshot.farmCommit")
    require_hex64(contract_sha256, "compatibilitySnapshot.contractSha256")
    snapshot_id = compatibility_snapshot_id(
        contract_sha256,
        runtime_commit,
        source_commit,
        farm_commit,
        upstreams,
    )

    packs: list[dict[str, Any]] = []
    for language in REQUIRED_PACK_FILES:
        logical = load_json(dist / f"miyorare-{language}-pack.json")
        shards: list[dict[str, Any]] = []
        for shard in logical.get("shards") or []:
            asset_name = shard.get("assetName")
            if not isinstance(asset_name, str):
                raise ManifestError(f"logical {language} pack has an invalid shard asset")
            asset = dist / asset_name
            if not asset.is_file():
                raise ManifestError(f"missing release asset: {asset_name}")
            shards.append(
                {
                    "provider": shard["provider"],
                    "pluginId": shard["pluginId"],
                    "assetName": asset.name,
                    "size": asset.stat().st_size,
                    "sha256": sha256(asset),
                    "sourceCount": shard["sourceCount"],
                }
            )
        packs.append(
            {
                "pluginId": logical["packId"],
                "language": logical["language"],
                "sourceCount": logical["sourceCount"],
                "shards": shards,
            }
        )

    manifest = {
        "schema": 3,
        "version": version,
        "tag": f"miyorare-sources-v{version}",
        "compatibility": {
            "channel": "stable",
            "tsukiApi": tsuki_api,
            "compatibilityEpoch": compatibility_epoch,
            "minMiyorareVersionCode": runtime_version_code,
            "maxMiyorareVersionCode": None,
            "requiredLogicalPacks": list(REQUIRED_LOGICAL_PACKS),
            "releaseLockRequired": True,
        },
        "sourceRepository": "Noirero/Miyorare",
        "sourceBranch": "beta",
        "sourceCommit": source_commit,
        "runtimeCompatibility": {
            "repository": "Noirero/Miyorare",
            "branch": "main",
            "commit": runtime_commit,
            "versionCode": runtime_version_code,
            "tsukiApi": tsuki_api,
        },
        "upstreams": upstreams,
        "compatibilitySnapshotId": snapshot_id,
        "compatibilitySnapshot": {
            "schemaVersion": 1,
            "algorithm": "sha256",
            "contractSha256": contract_sha256,
            "farmCommit": farm_commit,
        },
        "packs": packs,
    }
    validate(
        manifest,
        contract,
        expected_contract_sha256=contract_sha256,
        require_compatibility_snapshot=True,
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_generate = sub.add_parser("generate")
    p_generate.add_argument("--dist", type=Path, required=True)
    p_generate.add_argument("--contract", type=Path, required=True)
    p_generate.add_argument("--version", required=True)
    p_generate.add_argument("--source-commit", required=True)
    p_generate.add_argument("--runtime-commit", required=True)
    p_generate.add_argument("--runtime-version-code", type=int, required=True)
    p_generate.add_argument("--tsuki-api", required=True)
    p_generate.add_argument("--compatibility-epoch", type=int, required=True)
    p_generate.add_argument("--uma-commit", required=True)
    p_generate.add_argument("--gekkoushi-commit", required=True)
    p_generate.add_argument("--keiyoushi-commit", required=True)
    p_generate.add_argument("--farm-commit", required=True)
    p_generate.add_argument("--output", type=Path, required=True)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--manifest", type=Path, required=True)
    p_validate.add_argument("--contract", type=Path, required=True)
    p_validate.add_argument("--tag")
    p_validate.add_argument("--require-compatibility-snapshot", action="store_true")

    args = parser.parse_args()
    try:
        contract = load_json(args.contract)
        if args.command == "generate":
            manifest = generate(
                dist=args.dist,
                version=args.version,
                source_commit=args.source_commit.lower(),
                runtime_commit=args.runtime_commit.lower(),
                runtime_version_code=args.runtime_version_code,
                tsuki_api=args.tsuki_api,
                compatibility_epoch=args.compatibility_epoch,
                upstreams={
                    "uma": args.uma_commit.lower(),
                    "gekkoushi": args.gekkoushi_commit.lower(),
                    "keiyoushi": args.keiyoushi_commit.lower(),
                },
                farm_commit=args.farm_commit.lower(),
                contract_sha256=sha256(args.contract),
                contract=contract,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            manifest = load_json(args.manifest)
            validate(
                manifest,
                contract,
                expected_tag=args.tag,
                expected_contract_sha256=sha256(args.contract),
                require_compatibility_snapshot=args.require_compatibility_snapshot,
            )
    except (OSError, KeyError, ManifestError) as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
