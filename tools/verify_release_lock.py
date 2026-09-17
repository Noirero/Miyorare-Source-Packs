#!/usr/bin/env python3
"""Verify that a sealed Source Pack GitHub release still matches its immutable lock.

Cryptographic authenticity of the lock is verified separately with `gh attestation verify`.
This helper proves that every non-seal release asset is exactly the name, byte size, and SHA-256
recorded by that signed lock, with no additions, removals, or replacements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SEAL_FILES = {"miyorare-release-lock.json", "miyorare-release-lock.sha256"}


class ReleaseLockError(ValueError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(directory: Path, expected_tag: str | None = None) -> dict:
    lock_path = directory / "miyorare-release-lock.json"
    checksum_path = directory / "miyorare-release-lock.sha256"
    if not lock_path.is_file() or not checksum_path.is_file():
        raise ReleaseLockError("release is not sealed")

    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schemaVersion") != 1 or lock.get("kind") != "MIYORARE_SOURCE_PACK_RELEASE_LOCK":
        raise ReleaseLockError("unsupported release lock schema/kind")
    if lock.get("immutable") is not True:
        raise ReleaseLockError("release lock does not declare immutable=true")
    if expected_tag is not None and lock.get("tag") != expected_tag:
        raise ReleaseLockError("release lock tag mismatch")

    checksum_line = checksum_path.read_text(encoding="utf-8").strip().split()
    if len(checksum_line) < 2 or checksum_line[1] != "miyorare-release-lock.json":
        raise ReleaseLockError("invalid release lock checksum file")
    if checksum_line[0].lower() != sha256(lock_path):
        raise ReleaseLockError("release lock SHA-256 mismatch")

    locked_assets = lock.get("assets")
    if not isinstance(locked_assets, list) or not locked_assets:
        raise ReleaseLockError("release lock binds no assets")

    expected: dict[str, tuple[int, str]] = {}
    for item in locked_assets:
        if not isinstance(item, dict):
            raise ReleaseLockError("invalid release lock asset entry")
        name = item.get("name")
        size = item.get("size")
        digest = item.get("sha256")
        if (
            not isinstance(name, str)
            or not name
            or name in SEAL_FILES
            or Path(name).name != name
            or not isinstance(size, int)
            or size < 1
            or not isinstance(digest, str)
            or len(digest) != 64
        ):
            raise ReleaseLockError(f"invalid locked asset metadata: {item!r}")
        if name in expected:
            raise ReleaseLockError(f"duplicate locked asset: {name}")
        expected[name] = (size, digest.lower())

    actual_names = {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name not in SEAL_FILES
    }
    expected_names = set(expected)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise ReleaseLockError(f"release asset set changed; missing={missing}, extra={extra}")

    for name, (expected_size, expected_digest) in sorted(expected.items()):
        path = directory / name
        if path.stat().st_size != expected_size:
            raise ReleaseLockError(f"release asset size changed: {name}")
        if sha256(path) != expected_digest:
            raise ReleaseLockError(f"release asset SHA-256 changed: {name}")

    manifest = directory / "miyorare-source-packs.json"
    if manifest.is_file():
        manifest_digest = lock.get("releaseManifestSha256")
        if not isinstance(manifest_digest, str) or sha256(manifest) != manifest_digest.lower():
            raise ReleaseLockError("release manifest no longer matches release lock")

    return {
        "tag": lock.get("tag"),
        "assetCount": len(expected),
        "releaseManifestSha256": lock.get("releaseManifestSha256"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, type=Path)
    parser.add_argument("--tag")
    args = parser.parse_args()
    try:
        result = verify(args.dir, args.tag)
    except (OSError, json.JSONDecodeError, ReleaseLockError) as exc:
        print(f"error: {exc}")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
