#!/usr/bin/env python3
"""Generate and collect fail-closed live parser smoke tests for PENDING sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

PROFILE_READY = "PARSER_PENDING"
PACKAGE_RE = re.compile(r"(?m)^\s*package\s+([A-Za-z0-9_.]+)\s*$")
CLASS_RE = re.compile(
    r"(?:internal\s+|public\s+|private\s+|protected\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*MangaLoaderContext",
    re.S,
)


def load(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_name(canonical_id: str, provider: str) -> str:
    digest = hashlib.sha256(f"{canonical_id}|{provider}".encode()).hexdigest()[:12]
    return f"AutoLive_{provider}_{digest}"


def profile_map(profile_results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = profile_results.get("results", [])
    return {
        row["canonicalId"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("canonicalId"), str)
    }


def detect_tsuki_class(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    package = PACKAGE_RE.search(text)
    klass = CLASS_RE.search(text)
    if package is None or klass is None:
        raise ValueError(f"could not resolve MangaLoaderContext parser class from {path}")
    return f"{package.group(1)}.{klass.group(1)}"


def live_context_source() -> str:
    return r'''package compatibilityfarm

import java.util.concurrent.TimeUnit
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Response
import tsuki.MangaLoaderContext
import tsuki.MangaParser
import tsuki.bitmap.Bitmap
import tsuki.config.ConfigKey
import tsuki.config.MangaSourceConfig
import tsuki.model.MangaSource

internal class LiveMangaLoaderContext : MangaLoaderContext() {
    private val cookies = mutableListOf<Cookie>()

    override val cookieJar: CookieJar = object : CookieJar {
        override fun saveFromResponse(url: HttpUrl, incoming: List<Cookie>) {
            incoming.forEach { cookie ->
                cookies.removeAll { it.name == cookie.name && it.domain == cookie.domain && it.path == cookie.path }
                cookies += cookie
            }
        }
        override fun loadForRequest(url: HttpUrl): List<Cookie> = cookies.filter { it.matches(url) }
    }

    override val httpClient: OkHttpClient = OkHttpClient.Builder()
        .cookieJar(cookieJar)
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS)
        .callTimeout(35, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    override fun newParserInstance(source: MangaSource): MangaParser = error("not used by live onboarding harness")
    override fun getParserSources(): List<MangaSource> = emptyList()

    @Deprecated("Provide a base url")
    override suspend fun evaluateJs(script: String): String? = null
    override suspend fun evaluateJs(baseUrl: String, script: String): String? = null

    override fun getConfig(source: MangaSource): MangaSourceConfig = object : MangaSourceConfig {
        override fun <T> get(key: ConfigKey<T>): T = key.defaultValue
    }

    override fun getDefaultUserAgent(): String =
        "Mozilla/5.0 (X11; Linux x86_64) MiyorareCompatibilityFarm/1.0"

    override fun redrawImageResponse(response: Response, redraw: (Bitmap) -> Bitmap): Response = response
    override fun createBitmap(width: Int, height: Int): Bitmap = error("bitmap creation not used by parser smoke")
}
'''


def tsuki_test_source(test_class: str, fqcn: str) -> str:
    return f'''package compatibilityfarm

import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.MangaLoaderContext
import tsuki.MangaParser
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder

internal class {test_class} {{
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {{
        val type = Class.forName("{fqcn}")
        val ctor = type.getDeclaredConstructor(MangaLoaderContext::class.java).apply {{ isAccessible = true }}
        val parser = ctor.newInstance(LiveMangaLoaderContext()) as MangaParser

        var browse = emptyList<tsuki.model.Manga>()
        var lastFailure: Throwable? = null
        for (order in listOf(SortOrder.UPDATED, SortOrder.POPULARITY, SortOrder.NEWEST, SortOrder.ALPHABETICAL)) {{
            try {{
                val candidate = parser.getList(0, order, MangaListFilter())
                if (candidate.isNotEmpty()) {{
                    browse = candidate
                    break
                }}
            }} catch (t: Throwable) {{
                lastFailure = t
            }}
        }}
        assertTrue(browse.isNotEmpty(), "live browse returned no manga; lastFailure=${{lastFailure?.javaClass?.simpleName}}")

        val details = parser.getDetails(browse.first())
        assertTrue(details.title.isNotBlank(), "details title is blank")
        val chapters = details.chapters
        assertNotNull(chapters, "details returned null chapters")
        assertTrue(chapters!!.isNotEmpty(), "details returned no chapters")

        val pages = parser.getPages(chapters.first())
        assertTrue(pages.isNotEmpty(), "first chapter returned no pages")
        assertTrue(pages.first().url.isNotBlank(), "first page URL is blank")
    }}
}}
'''


def keiyoushi_test_source(test_class: str) -> str:
    return f'''package compatibilityfarm

import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import keiyoushi.source.KeiSource
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.lang.reflect.Method
import java.util.concurrent.TimeUnit

class {test_class} {{
    private val source: Any by lazy {{
        val generated = Class.forName("keiyoushi.source.Generated")
        val instance = generated.getDeclaredConstructor().apply {{ isAccessible = true }}.newInstance()
        val createSources = findMethodOrNull(instance, "createSources", emptyArray())
        if (createSources == null) {{
            instance
        }} else {{
            createSources.isAccessible = true
            val sources = createSources.invoke(instance) as? List<*>
                ?: error("createSources did not return a list")
            sources.firstOrNull() ?: error("createSources returned no sources")
        }}
    }}
    private val client = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .callTimeout(35, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {{
        val actual = source
        if (actual is KeiSource) {{
            val popular = actual.getPopularManga(1)
            assertFalse("live browse returned no manga", popular.mangas.isEmpty())
            val manga = popular.mangas.first()

            val update = actual.fetchMangaUpdate(
                manga = manga,
                chapters = emptyList(),
                fetchDetails = true,
                fetchChapters = true,
            )
            assertTrue("details title is blank", update.manga.title.isNotBlank())
            assertFalse("details returned no chapters", update.chapters.isEmpty())

            val pages = actual.getPageList(update.chapters.first())
            assertFalse("first chapter returned no pages", pages.isEmpty())
        }} else {{
            val popularRequest = call("popularMangaRequest", arrayOf(Int::class.javaPrimitiveType!!), 1) as Request
            val popular = execute(popularRequest) {{ response ->
                call("popularMangaParse", arrayOf(Response::class.java), response) as MangasPage
            }}
            assertFalse("live browse returned no manga", popular.mangas.isEmpty())
            val manga = popular.mangas.first()

            val detailsRequest = call("mangaDetailsRequest", arrayOf(SManga::class.java), manga) as Request
            val details = execute(detailsRequest) {{ response ->
                call("mangaDetailsParse", arrayOf(Response::class.java), response) as SManga
            }}
            assertTrue("details title is blank", details.title.isNotBlank())
            if (details.url.isBlank()) details.url = manga.url

            val chapterRequest = call("chapterListRequest", arrayOf(SManga::class.java), details) as Request
            val chapters = execute(chapterRequest) {{ response ->
                @Suppress("UNCHECKED_CAST")
                call("chapterListParse", arrayOf(Response::class.java), response) as List<SChapter>
            }}
            assertFalse("details returned no chapters", chapters.isEmpty())

            val pageRequest = call("pageListRequest", arrayOf(SChapter::class.java), chapters.first()) as Request
            val pages = execute(pageRequest) {{ response ->
                call("pageListParse", arrayOf(Response::class.java), response) as List<*>
            }}
            assertFalse("first chapter returned no pages", pages.isEmpty())
        }}
    }}

    private fun <T> execute(request: Request, parser: (Response) -> T): T =
        client.newCall(request).execute().use {{ response ->
            check(response.code < 500) {{ "HTTP ${{response.code}} for ${{request.url}}" }}
            parser(response)
        }}

    private fun call(name: String, parameterTypes: Array<Class<*>>, vararg args: Any?): Any? {{
        val method = findMethod(name, parameterTypes)
        method.isAccessible = true
        return method.invoke(source, *args)
    }}

    private fun findMethod(name: String, parameterTypes: Array<Class<*>>): Method =
        findMethodOrNull(source, name, parameterTypes)
            ?: error("Method $name not found on ${{source.javaClass.name}}")

    private fun findMethodOrNull(target: Any, name: String, parameterTypes: Array<Class<*>>): Method? {{
        // Public inherited/interface methods (notably Generated SourceFactory#createSources)
        // are visible through getMethod() but not necessarily getDeclaredMethod().
        try {{
            return target.javaClass.getMethod(name, *parameterTypes)
        }} catch (_: NoSuchMethodException) {{
            // Fall through to protected/private source methods on the class hierarchy.
        }}
        var type: Class<*>? = target.javaClass
        while (type != null) {{
            try {{
                return type.getDeclaredMethod(name, *parameterTypes)
            }} catch (_: NoSuchMethodException) {{
                type = type.superclass
            }}
        }}
        return null
    }}
}}
'''


def generate(
    plan: dict[str, Any],
    profile_results: dict[str, Any],
    provider: str,
    provider_root: Path,
) -> dict[str, Any]:
    profiles = profile_map(profile_results)
    tests: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    if provider in {"uma", "gekkoushi"}:
        target = provider_root / "src/test/kotlin/compatibilityfarm"
        target.mkdir(parents=True, exist_ok=True)
        (target / "LiveMangaLoaderContext.kt").write_text(live_context_source(), encoding="utf-8")

    for item in plan.get("items", []):
        canonical_id = item.get("canonicalId")
        profile = profiles.get(canonical_id, {})
        if profile.get("state") != PROFILE_READY or provider not in item.get("providers", []):
            continue
        auth_type = profile.get("authType")
        test_class = safe_name(canonical_id, provider)
        if auth_type != "NO_AUTH":
            blocked.append(
                {
                    "canonicalId": canonical_id,
                    "provider": provider,
                    "status": "FAIL",
                    "reason": f"AUTH_REQUIRED:{auth_type}",
                    "testClass": f"compatibilityfarm.{test_class}",
                }
            )
            continue
        identity = item.get("upstreamIdentities", {}).get(provider, {})
        locator = identity.get("module") if provider == "keiyoushi" else identity.get("file")
        if not isinstance(locator, str) or not locator:
            blocked.append(
                {
                    "canonicalId": canonical_id,
                    "provider": provider,
                    "status": "FAIL",
                    "reason": "MISSING_LOCATOR",
                    "testClass": f"compatibilityfarm.{test_class}",
                }
            )
            continue
        try:
            if provider == "keiyoushi":
                module = provider_root / locator
                if not module.is_dir():
                    raise ValueError("module missing")
                target = module / "compatibility-farm-test"
                target.mkdir(parents=True, exist_ok=True)
                (target / f"{test_class}.kt").write_text(
                    keiyoushi_test_source(test_class), encoding="utf-8"
                )
                tests.append(
                    {
                        "canonicalId": canonical_id,
                        "provider": provider,
                        "locator": locator,
                        "testClass": f"compatibilityfarm.{test_class}",
                        "resultsDir": str(module / "build/test-results/testDebugUnitTest"),
                    }
                )
            else:
                source_path = provider_root / locator
                fqcn = detect_tsuki_class(source_path)
                target = provider_root / "src/test/kotlin/compatibilityfarm"
                (target / f"{test_class}.kt").write_text(
                    tsuki_test_source(test_class, fqcn), encoding="utf-8"
                )
                tests.append(
                    {
                        "canonicalId": canonical_id,
                        "provider": provider,
                        "locator": locator,
                        "fqcn": fqcn,
                        "testClass": f"compatibilityfarm.{test_class}",
                        "resultsDir": str(provider_root / "build/test-results/test"),
                    }
                )
        except (OSError, ValueError) as exc:
            blocked.append(
                {
                    "canonicalId": canonical_id,
                    "provider": provider,
                    "status": "FAIL",
                    "reason": f"HARNESS_GENERATION:{type(exc).__name__}:{exc}",
                    "testClass": f"compatibilityfarm.{test_class}",
                }
            )

    return {"schemaVersion": 1, "provider": provider, "tests": tests, "blocked": blocked}


def junit_suite(results_dir: Path, test_class: str) -> dict[str, Any] | None:
    if not results_dir.is_dir():
        return None
    for path in sorted(results_dir.glob("TEST-*.xml")):
        root = ET.parse(path).getroot()
        if root.attrib.get("name") != test_class:
            continue
        failure_type: str | None = None
        failure_message: str | None = None
        for testcase in root.findall("testcase"):
            failure = testcase.find("failure")
            if failure is None:
                failure = testcase.find("error")
            if failure is None:
                continue
            failure_type = failure.attrib.get("type") or None
            failure_message = failure.attrib.get("message") or (failure.text or "").strip() or None
            if failure_message:
                failure_message = " ".join(failure_message.split())[:1000]
            break
        return {
            "tests": int(root.attrib.get("tests", "0")),
            "failures": int(root.attrib.get("failures", "0")),
            "errors": int(root.attrib.get("errors", "0")),
            "skipped": int(root.attrib.get("skipped", "0")),
            "failureType": failure_type,
            "failureMessage": failure_message,
        }
    return None


def collect(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for manifest in manifests:
        for blocked in manifest.get("blocked", []):
            results.append({**blocked, "parserExecution": False})
        for test in manifest.get("tests", []):
            try:
                suite = junit_suite(Path(test["resultsDir"]), test["testClass"])
            except (OSError, ET.ParseError, ValueError) as exc:
                suite = None
                error = f"JUNIT_PARSE:{type(exc).__name__}:{exc}"
            else:
                error = "JUNIT_SUITE_MISSING"
            if suite is None:
                results.append(
                    {
                        **test,
                        "status": "FAIL",
                        "parserExecution": False,
                        "reason": error,
                    }
                )
                continue
            passed = (
                suite["tests"] > 0
                and suite["failures"] == 0
                and suite["errors"] == 0
                and suite["skipped"] < suite["tests"]
            )
            results.append(
                {
                    **test,
                    **suite,
                    "status": "PASS" if passed else "FAIL",
                    "parserExecution": True,
                    "detailsTraversal": passed,
                    "chapterTraversal": passed,
                    "pageExtraction": passed,
                }
            )
    return {"schemaVersion": 1, "executionMode": "real-live-parser", "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--plan", required=True)
    generate_parser.add_argument("--profile-results", required=True)
    generate_parser.add_argument("--provider", choices=("uma", "gekkoushi", "keiyoushi"), required=True)
    generate_parser.add_argument("--provider-root", required=True)
    generate_parser.add_argument("--output", required=True)

    collect_parser = sub.add_parser("collect")
    collect_parser.add_argument("--manifest", action="append", required=True)
    collect_parser.add_argument("--output", required=True)

    args = parser.parse_args()
    if args.command == "generate":
        save(
            args.output,
            generate(
                load(args.plan),
                load(args.profile_results),
                args.provider,
                Path(args.provider_root).resolve(),
            ),
        )
    else:
        save(args.output, collect([load(path) for path in args.manifest]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
