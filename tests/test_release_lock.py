import hashlib
import importlib.util
import json
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "verify_release_lock",
    Path(__file__).parents[1] / "tools" / "verify_release_lock.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def sealed_release(tmp_path: Path) -> Path:
    asset = tmp_path / "pack.jar"
    asset.write_bytes(b"source-pack")
    manifest = tmp_path / "miyorare-source-packs.json"
    manifest.write_text('{"schema":2}\n', encoding="utf-8")
    lock = {
        "schemaVersion": 1,
        "kind": "MIYORARE_SOURCE_PACK_RELEASE_LOCK",
        "immutable": True,
        "tag": "miyorare-sources-v9.9.9",
        "releaseManifestSha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "assets": [],
    }
    for path in (asset, manifest):
        lock["assets"].append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    lock_path = tmp_path / "miyorare-release-lock.json"
    lock_path.write_text(json.dumps(lock, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    (tmp_path / "miyorare-release-lock.sha256").write_text(
        f"{digest}  miyorare-release-lock.json\n",
        encoding="utf-8",
    )
    return asset


def test_valid_lock_passes(tmp_path):
    sealed_release(tmp_path)
    result = MODULE.verify(tmp_path, "miyorare-sources-v9.9.9")
    assert result["assetCount"] == 2


def test_replaced_asset_fails(tmp_path):
    asset = sealed_release(tmp_path)
    asset.write_bytes(b"tampered")
    try:
        MODULE.verify(tmp_path, "miyorare-sources-v9.9.9")
    except MODULE.ReleaseLockError:
        return
    raise AssertionError("tampered release unexpectedly passed")


def test_added_asset_fails(tmp_path):
    sealed_release(tmp_path)
    (tmp_path / "unexpected.txt").write_text("extra", encoding="utf-8")
    try:
        MODULE.verify(tmp_path, "miyorare-sources-v9.9.9")
    except MODULE.ReleaseLockError:
        return
    raise AssertionError("release with extra asset unexpectedly passed")
