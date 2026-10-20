#!/usr/bin/env python3
"""Prepare a Kotatsu-Redo checkout as a Tsuki 1.0.5 compatibility plugin.

The transformation is intentionally build-only. Upstream source remains authoritative and pinned by
compatibility/kotatsu-provider.v1.json. Shared Tsuki ABI files are removed from the disposable
checkout so every remaining parser is compiled against the exact host ABI instead of silently
shipping a second copy of the runtime contract.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

FROM_NAMESPACE = "org.koitharu.kotatsu.parsers"
TO_NAMESPACE = "tsuki"
HOST_JAR_PROPERTY = "miyorareHostTsukiJar"


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"error: {message}")


def replace_text(path: Path, old: str, new: str) -> int:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count:
        path.write_text(text.replace(old, new), encoding="utf-8")
    return count


def remove_host_overlaps(upstream: Path, host: Path) -> list[str]:
    upstream_root = upstream / "src/main/kotlin/org/koitharu/kotatsu/parsers"
    host_root = host / "src/main/kotlin/tsuki"
    if not upstream_root.is_dir():
        fail(f"missing Kotatsu parser source root: {upstream_root}")
    if not host_root.is_dir():
        fail(f"missing Tsuki host source root: {host_root}")

    removed: list[str] = []
    for host_file in sorted(host_root.rglob("*.kt")):
        relative = host_file.relative_to(host_root)
        candidate = upstream_root / relative
        if candidate.is_file():
            candidate.unlink()
            removed.append(relative.as_posix())
    return removed


def patch_build(upstream: Path) -> None:
    build = upstream / "build.gradle.kts"
    text = build.read_text(encoding="utf-8")
    marker = "dependencies {\n"
    dependency = (
        f'    compileOnly(files(providers.gradleProperty("{HOST_JAR_PROPERTY}").get()))\n'
    )
    if dependency not in text:
        if marker not in text:
            fail("could not find root dependencies block")
        text = text.replace(marker, marker + dependency, 1)

    task_marker = "miyorare-compile-classpath.txt"
    if task_marker not in text:
        text += """

// Miyorare compatibility pilot: expose the exact classpath used for D8 validation.
tasks.register("writeMiyorareCompileClasspath") {
    val output = layout.buildDirectory.file("miyorare-compile-classpath.txt")
    outputs.file(output)
    doLast {
        output.get().asFile.writeText(
            configurations.compileClasspath.get().files.joinToString(System.getProperty("path.separator")),
        )
    }
}
"""
    build.write_text(text, encoding="utf-8")


def transform_namespaces(upstream: Path) -> int:
    roots = [
        upstream / "src/main/kotlin",
        upstream / "kotatsu-parsers-ksp/src/main/kotlin",
    ]
    changed = 0
    for root in roots:
        if not root.is_dir():
            fail(f"missing source root: {root}")
        for path in root.rglob("*.kt"):
            changed += replace_text(path, FROM_NAMESPACE, TO_NAMESPACE)

    changed += replace_text(upstream / "build.gradle.kts", FROM_NAMESPACE, TO_NAMESPACE)
    return changed


def verify_no_duplicate_host_sources(upstream: Path, host: Path) -> None:
    upstream_root = upstream / "src/main/kotlin/org/koitharu/kotatsu/parsers"
    host_root = host / "src/main/kotlin/tsuki"
    duplicates = [
        path.relative_to(upstream_root).as_posix()
        for path in upstream_root.rglob("*.kt")
        if (host_root / path.relative_to(upstream_root)).is_file()
    ]
    if duplicates:
        fail("shared Tsuki sources remain in shard: " + ", ".join(sorted(duplicates)[:20]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--host-tsuki", required=True, type=Path)
    parser.add_argument("--metadata-out", required=True, type=Path)
    args = parser.parse_args()

    upstream = args.upstream.resolve()
    host = args.host_tsuki.resolve()
    removed = remove_host_overlaps(upstream, host)
    replacements = transform_namespaces(upstream)
    patch_build(upstream)
    verify_no_duplicate_host_sources(upstream, host)

    if replacements < 100:
        fail(f"unexpectedly small namespace transformation: {replacements} replacements")

    metadata = {
        "schema": 1,
        "namespaceFrom": FROM_NAMESPACE,
        "namespaceTo": TO_NAMESPACE,
        "hostJarProperty": HOST_JAR_PROPERTY,
        "removedSharedSourceCount": len(removed),
        "namespaceReplacementCount": replacements,
        "removedSharedSources": removed,
    }
    args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_out.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(
        f"prepared Kotatsu provider: removed {len(removed)} shared ABI files; "
        f"rewrote {replacements} namespace references"
    )


if __name__ == "__main__":
    main()
