#!/usr/bin/env python3
"""Prepare a Kotatsu-Redo checkout as an isolated runtime with a Tsuki 1.0.5 facade.

The upstream implementation is relocated as one intact module into a private plugin namespace.
Only the tiny generated facade is linked to Miyorare's parent-loaded Tsuki ABI. This avoids both
replacing the host's existing parser dependency and splitting modern Kotatsu model/core classes
across module boundaries.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

FROM_NAMESPACE = "org.koitharu.kotatsu.parsers"
TO_NAMESPACE = "miyorare.kotatsuredo"
HOST_JAR_PROPERTY = "miyorareHostTsukiJar"
FACADE_PROVIDER = "miyorare.kotatsuredo.ksp.MiyorareFacadeProcessorProvider"


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"error: {message}")


def replace_text(path: Path, old: str, new: str) -> int:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count:
        path.write_text(text.replace(old, new), encoding="utf-8")
    return count


def patch_build(upstream: Path) -> None:
    build = upstream / "build.gradle.kts"
    text = build.read_text(encoding="utf-8")
    marker = "dependencies {\n"
    dependency = f'    compileOnly(files(providers.gradleProperty("{HOST_JAR_PROPERTY}").get()))\n'
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

    service = (
        upstream
        / "kotatsu-parsers-ksp/src/main/resources/META-INF/services"
        / "com.google.devtools.ksp.processing.SymbolProcessorProvider"
    )
    if not service.is_file():
        fail(f"missing KSP service descriptor: {service}")
    changed += replace_text(service, FROM_NAMESPACE, TO_NAMESPACE)
    providers = [line.strip() for line in service.read_text(encoding="utf-8").splitlines() if line.strip()]
    if FACADE_PROVIDER not in providers:
        providers.append(FACADE_PROVIDER)
    service.write_text("\n".join(providers) + "\n", encoding="utf-8")

    changed += replace_text(upstream / "build.gradle.kts", FROM_NAMESPACE, TO_NAMESPACE)
    return changed


def verify_transform(upstream: Path) -> None:
    offenders: list[str] = []
    for root in (
        upstream / "src/main/kotlin",
        upstream / "kotatsu-parsers-ksp/src/main/kotlin",
    ):
        for path in root.rglob("*.kt"):
            if FROM_NAMESPACE in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(upstream)))
    if offenders:
        fail("unrelocated Kotatsu namespace remains in: " + ", ".join(offenders[:20]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--metadata-out", required=True, type=Path)
    args = parser.parse_args()

    upstream = args.upstream.resolve()
    replacements = transform_namespaces(upstream)
    patch_build(upstream)
    verify_transform(upstream)

    if replacements < 100:
        fail(f"unexpectedly small namespace transformation: {replacements} replacements")

    metadata = {
        "schema": 2,
        "namespaceFrom": FROM_NAMESPACE,
        "namespaceTo": TO_NAMESPACE,
        "hostJarProperty": HOST_JAR_PROPERTY,
        "facadeProcessor": FACADE_PROVIDER,
        "namespaceReplacementCount": replacements,
        "sharedAbiRemovalCount": 0,
        "strategy": "private-runtime-with-tsuki-facade",
    }
    args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_out.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(
        f"prepared isolated Kotatsu provider: rewrote {replacements} namespace references; "
        "kept modern runtime/model classes intact"
    )


if __name__ == "__main__":
    main()
