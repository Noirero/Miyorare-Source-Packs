#!/usr/bin/env python3
"""Materialize the Keiyoushi host shim for real-live PENDING onboarding tests.

The authoritative Compatibility Farm runtime remains deterministic. This helper copies
that runtime into a disposable module test tree and changes only the copied
NetworkHelper wiring so requests use normal OkHttp networking.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


FIXTURE_LINE = "        .addInterceptor(DeterministicFixtureInterceptor())\n"


def materialize(runtime: Path, target: Path) -> dict[str, str]:
    source_factory = runtime / "eu/kanade/tachiyomi/source/SourceFactoryShim.kt"
    network = runtime / "eu/kanade/tachiyomi/network/NetworkShim.kt"
    if not source_factory.is_file():
        raise ValueError("SourceFactoryShim.kt missing from authoritative runtime")
    if not network.is_file():
        raise ValueError("NetworkShim.kt missing from authoritative runtime")

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(runtime, target)

    copied_network = target / "eu/kanade/tachiyomi/network/NetworkShim.kt"
    text = copied_network.read_text(encoding="utf-8")
    if FIXTURE_LINE not in text:
        raise ValueError("deterministic fixture interceptor marker missing")
    live = text.replace(FIXTURE_LINE, "", 1)
    if FIXTURE_LINE in live:
        raise ValueError("more than one deterministic fixture interceptor marker found")
    copied_network.write_text(live, encoding="utf-8")

    # Verify source was not modified and copied ABI still exists.
    if FIXTURE_LINE not in network.read_text(encoding="utf-8"):
        raise ValueError("authoritative deterministic runtime was unexpectedly modified")
    if not (target / "eu/kanade/tachiyomi/source/SourceFactoryShim.kt").is_file():
        raise ValueError("live runtime lost SourceFactory host ABI")

    return {
        "mode": "real-live-network",
        "sourceRuntime": str(runtime),
        "targetRuntime": str(target),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    result = materialize(args.runtime.resolve(), args.target.resolve())
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
