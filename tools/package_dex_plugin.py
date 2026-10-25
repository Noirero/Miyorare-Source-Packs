#!/usr/bin/env python3
"""Package D8 output plus non-class resources into a plugin JAR."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-jar", required=True, type=Path)
    parser.add_argument("--dex-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    dex_files = sorted(args.dex_dir.glob("*.dex"))
    if not dex_files:
        raise SystemExit("error: D8 produced no dex files")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for dex in dex_files:
            out.write(dex, dex.name)
            seen.add(dex.name)

        with zipfile.ZipFile(args.input_jar) as source:
            for info in source.infolist():
                name = info.filename
                if info.is_dir() or name.endswith(".class") or name == "META-INF/MANIFEST.MF":
                    continue
                if name in seen:
                    raise SystemExit(f"error: duplicate plugin entry: {name}")
                out.writestr(name, source.read(info))
                seen.add(name)

    if args.output.stat().st_size <= 0:
        raise SystemExit("error: packaged plugin is empty")
    print(f"packaged {args.output} with {len(dex_files)} dex file(s)")


if __name__ == "__main__":
    main()
