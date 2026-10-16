package compatibilityfarm

import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.network.DeterministicNetwork
import eu.kanade.tachiyomi.network.DeterministicNetwork.FixtureResponse
import keiyoushi.source.KeiSource
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.lang.reflect.Method
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption

class KeiyoushiAquaMangaParserHarnessTest {
    private val source: Any by lazy {
        val generated = Class.forName("keiyoushi.source.Generated")
        val coroutineApi = generateSequence<Class<*>>(generated) { it.superclass }
            .any { it.simpleName == "MadaraNoAjax" }
        installMadaraEnglishBundle(if (coroutineApi) "madara" else "madaralegacy")
        generated.getDeclaredConstructor().apply { isAccessible = true }.newInstance()
    }

    @Test
    fun executesPinnedAquaParserAgainstDeterministicResponses() {
        System.getProperty("compatibility.candidate")?.let {
            assertEquals("Unexpected Aqua API generation for the pinned revision", it.toBoolean(), source is KeiSource)
        }
        if (source is KeiSource) {
            executeCoroutineMadara(source as KeiSource)
            return
        }
        assertEquals(".aqua-archive-card", call("popularMangaSelector", emptyArray()))
        assertEquals("a.next", call("popularMangaNextPageSelector", emptyArray()))
        assertEquals(".aqua-series-info__title", call("getMangaDetailsSelectorTitle", emptyArray()))
        assertEquals(".aqua-ch-item", call("chapterListSelector", emptyArray()))

        val popularRequest = call(
            "popularMangaRequest",
            arrayOf(Int::class.javaPrimitiveType!!),
            1,
        ) as Request
        assertEquals("https://aquareader.org/manga/?m_orderby=views", popularRequest.url.toString())

        val popular = call(
            "popularMangaParse",
            arrayOf(Response::class.java),
            response(
                popularRequest.url.toString(),
                """
                <div class="aqua-archive-card">
                  <div class="aqua-archive-card__title">
                    <a href="https://aquareader.org/manga/alpha/">Alpha Aqua</a>
                  </div>
                  <img class="aqua-archive-card__cover" src="https://aquareader.org/covers/alpha.jpg" />
                </div>
                """.trimIndent(),
            ),
        ) as MangasPage
        assertFalse(popular.hasNextPage)
        assertEquals(1, popular.mangas.size)
        val manga = popular.mangas.single()
        assertEquals("Alpha Aqua", manga.title)
        assertEquals("/manga/alpha/", manga.url)
        assertEquals("https://aquareader.org/covers/alpha.jpg", manga.thumbnail_url)

        val searchRequest = call(
            "searchMangaRequest",
            arrayOf(Int::class.javaPrimitiveType!!, String::class.java, FilterList::class.java),
            1,
            "Alpha",
            FilterList(),
        ) as Request
        assertEquals("Alpha", searchRequest.url.queryParameter("s"))

        val search = call(
            "searchMangaParse",
            arrayOf(Response::class.java),
            response(
                searchRequest.url.toString(),
                """
                <html>
                  <head><title>Page 1 of 1</title></head>
                  <body>
                    <div class="c-tabs-item__content">
                      <div class="post-title">
                        <a href="https://aquareader.org/manga/alpha/">Alpha Aqua</a>
                      </div>
                      <img src="https://aquareader.org/covers/alpha.jpg" />
                    </div>
                  </body>
                </html>
                """.trimIndent(),
            ),
        ) as MangasPage
        assertFalse(search.hasNextPage)
        assertEquals(1, search.mangas.size)
        assertEquals("Alpha Aqua", search.mangas.single().title)

        val details = call(
            "mangaDetailsParse",
            arrayOf(Response::class.java),
            response(
                "https://aquareader.org/manga/alpha/",
                """
                <h1 class="aqua-series-info__title">Alpha Aqua</h1>
                <img class="aqua-series-cover__img" src="/covers/alpha.jpg" />
                <div class="aqua-series-synopsis"><p>Fixture Aqua synopsis.</p></div>
                <div class="aqua-series-meta__status">Ongoing</div>
                <a class="aqua-series-genre-pill" href="https://aquareader.org/manga-genre/action/">Action</a>
                <div class="aqua-series-info__creator-value"><a>Fixture Author</a></div>
                """.trimIndent(),
            ),
        ) as SManga
        assertEquals("Alpha Aqua", details.title)
        assertEquals("Fixture Author", details.author)
        assertEquals("Fixture Author", details.artist)
        assertEquals("Fixture Aqua synopsis.", details.description)
        assertEquals("Action", details.genre)
        assertEquals(SManga.ONGOING, details.status)
        assertEquals("https://aquareader.org/covers/alpha.jpg", details.thumbnail_url)

        val chapters = call(
            "chapterListParse",
            arrayOf(Response::class.java),
            response(
                "https://aquareader.org/manga/alpha/",
                """
                <a class="aqua-ch-item" href="https://aquareader.org/manga/alpha/chapter-1/">
                  <span class="aqua-ch-item__name">Chapter 1</span>
                  <span class="aqua-ch-item__time">January 01, 2026</span>
                </a>
                """.trimIndent(),
            ),
        ) as List<*>
        assertEquals(1, chapters.size)
        val chapter = chapters.single() as SChapter
        assertEquals("Chapter 1", chapter.name)
        assertEquals("https://aquareader.org/manga/alpha/chapter-1/", chapter.url)
        assertTrue(chapter.date_upload > 0L)

        val pages = call(
            "pageListParse",
            arrayOf(Response::class.java),
            response(
                "https://aquareader.org/manga/alpha/chapter-1/",
                """
                <div class="page-break"><img src="/pages/001.jpg" /></div>
                <div class="page-break"><img data-src="/pages/002.jpg" /></div>
                """.trimIndent(),
            ),
        ) as List<*>
        assertEquals(2, pages.size)
        val first = pages[0] as Page
        val second = pages[1] as Page
        assertEquals("https://aquareader.org/pages/001.jpg", first.imageUrl)
        assertEquals("https://aquareader.org/pages/002.jpg", second.imageUrl)
        assertEquals("https://aquareader.org/manga/alpha/chapter-1/", first.url)
        assertNotNull(second.imageUrl)

        val imageRequest = call(
            "imageRequest",
            arrayOf(Page::class.java),
            first,
        ) as Request
        assertEquals(first.imageUrl, imageRequest.url.toString())
        assertEquals(first.url, imageRequest.header("Referer"))
    }

    private fun executeCoroutineMadara(parser: KeiSource) = runBlocking {
        assertEquals("Aqua Manga", parser.name)
        assertEquals("en", parser.lang)
        assertEquals("https://aquareader.org", parser.baseUrl)
        assertEquals(false, call("getSupportsPostId", emptyArray()))
        val observed = mutableListOf<Request>()
        val canonical = "https://aquareader.org/manga/alpha-canonical/"
        DeterministicNetwork.install { request ->
            observed += request
            val url = request.url
            check(request.method == "GET" && url.host == "aquareader.org") {
                "Unexpected Aqua host/method: ${request.method} $url"
            }
            when {
                url.encodedPath == "/manga/" -> FixtureResponse(archiveHtml(next = true))
                url.encodedPath == "/manga/page/2/" ||
                    url.encodedPath == "/page/2/" -> FixtureResponse(archiveHtml(next = false))
                url.encodedPath == "/" && url.queryParameter("s") == "Alpha" ->
                    FixtureResponse(archiveHtml(next = true))
                url.encodedPath == "/manga/alpha/" -> FixtureResponse(
                    coroutineDetailsHtml(),
                    finalUrl = canonical,
                )
                url.encodedPath == "/manga/alpha-canonical/chapter-1/" ->
                    FixtureResponse(readerHtml())
                url.encodedPath == "/manga/alpha-canonical/chapter-2/" -> FixtureResponse(
                    if (url.queryParameter("style") == "list") readerHtml() else "<div id=\"single-pager\"></div>",
                )
                else -> error("Unexpected Aqua request (including post-ID fallback): $url")
            }
        }
        try {
            val popular = parser.getPopularManga(1)
            assertTrue(popular.hasNextPage)
            assertEquals(1, popular.mangas.size)
            val manga = popular.mangas.single()
            assertEquals("Alpha Aqua", manga.title)
            assertEquals("/manga/alpha/", manga.url)
            assertEquals("https://aquareader.org/covers/alpha.jpg", manga.thumbnail_url)
            assertEquals("https://aquareader.org/manga/alpha/", parser.getMangaUrl(manga))
            assertFalse(parser.getPopularManga(2).hasNextPage)
            assertTrue(parser.getLatestUpdates(1).hasNextPage)
            assertTrue(parser.getSearchMangaList(1, "Alpha", FilterList()).hasNextPage)
            val secondSearchPage = parser.getSearchMangaList(2, "Alpha", FilterList())
            assertFalse(secondSearchPage.hasNextPage)
            assertEquals("Alpha Aqua", secondSearchPage.mangas.single().title)

            // No post-ID is present in this response. The changed final URL must be
            // accepted by supportsPostId=false, rather than retried through ?p=.
            val update = parser.getMangaUpdate(manga, emptyList(), true, true)
            val details = update.manga
            assertEquals("Alpha Aqua", details.title)
            assertEquals("Fixture Author", details.author)
            assertEquals("Fixture Author", details.artist)
            assertEquals("Fixture Aqua synopsis.", details.description)
            assertEquals("Action", details.genre)
            assertEquals(SManga.ONGOING, details.status)
            assertEquals("https://aquareader.org/covers/alpha.jpg", details.thumbnail_url)
            assertEquals("/manga/alpha-canonical/", details.url)
            assertEquals(canonical, parser.getMangaUrl(details))
            assertTrue(details.initialized)
            assertEquals(2, update.chapters.size)
            update.chapters.forEachIndexed { index, chapter ->
                assertEquals("chapter-${index + 1}", chapter.url)
                assertEquals("Chapter ${index + 1}", chapter.name)
                assertTrue(chapter.date_upload > 0L)
                assertEquals("/manga/alpha-canonical/", chapter.memo["mangaPath"]?.jsonPrimitive?.content)
                assertEquals("${canonical}chapter-${index + 1}/", parser.getChapterUrl(chapter))
                val pages = parser.getPageList(chapter)
                assertEquals(2, pages.size)
                assertEquals(listOf(0, 1), pages.map { it.index })
                assertEquals("https://aquareader.org/pages/001.jpg", pages[0].imageUrl)
                assertEquals("https://aquareader.org/pages/002.jpg", pages[1].imageUrl)
                val expectedPageUrl = "${canonical}chapter-${index + 1}/" + if (index == 1) "?style=list" else ""
                assertEquals(expectedPageUrl, pages[0].url)
                val image = call("imageRequest", arrayOf(Page::class.java), pages[0]) as Request
                assertEquals(pages[0].imageUrl, image.url.toString())
                assertEquals(expectedPageUrl, image.header("Referer"))
            }
            assertTrue(observed.any { it.url.encodedPath == "/manga/" && it.url.queryParameter("m_orderby") == "views" })
            assertTrue(observed.any { it.url.encodedPath == "/manga/" && it.url.queryParameter("m_orderby") == "latest" })
            assertTrue(observed.any { it.url.encodedPath == "/manga/page/2/" && it.url.queryParameter("m_orderby") == "views" })
            assertTrue(observed.any { it.url.encodedPath == "/page/2/" && it.url.queryParameter("s") == "Alpha" && it.url.queryParameter("post_type") == "wp-manga" })
            assertEquals(1, observed.count { it.url.encodedPath == "/manga/alpha/" })
            assertTrue(observed.none { it.url.queryParameter("p") != null || it.url.encodedPath.contains("admin-ajax") })
        } finally {
            DeterministicNetwork.clear()
        }
    }

    private fun archiveHtml(next: Boolean) = """
        <div class="aqua-archive-card">
          <div class="aqua-archive-card__title"><a href="/manga/alpha/">Alpha Aqua</a></div>
          <img class="aqua-archive-card__cover" src="/covers/alpha.jpg">
        </div>
        ${if (next) "<a class=\"next\" href=\"/manga/page/2/\">Next</a>" else ""}
    """.trimIndent()

    private fun coroutineDetailsHtml() = """
        <h1 class="aqua-series-info__title">Alpha Aqua</h1>
        <img class="aqua-series-cover__img" src="/covers/alpha.jpg">
        <div class="aqua-series-synopsis"><p>Fixture Aqua synopsis.</p></div>
        <div class="aqua-series-meta__status">Ongoing</div>
        <a class="aqua-series-genre-pill" href="/manga-genre/action/">Action</a>
        <div class="aqua-series-info__creator-value"><a>Fixture Author</a></div>
        <div class="aqua-ch-item"><a href="/manga/alpha-canonical/chapter-1/">
          <span class="aqua-ch-item__name">Chapter 1</span></a>
          <span class="aqua-ch-item__time">January 01, 2026</span></div>
        <div class="aqua-ch-item"><a href="/manga/alpha-canonical/chapter-2/">
          <span class="aqua-ch-item__name">Chapter 2</span></a>
          <span class="aqua-ch-item__time">January 02, 2026</span></div>
    """.trimIndent()

    private fun readerHtml() = """
        <div class="page-break"><img src="/pages/001.jpg"></div>
        <div class="page-break"><img data-src="/pages/002.jpg"></div>
    """.trimIndent()

    private fun installMadaraEnglishBundle(theme: String) {
        val workingDir = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize()
        val sourceBundle = generateSequence(workingDir) { it.parent }
            .map { root ->
                root.resolve("lib-multisrc/$theme/assets/i18n/messages_en.properties")
            }
            .firstOrNull(Files::isRegularFile)
            ?: error("Pinned $theme English bundle not found from working directory: $workingDir")

        val classRoot = Path.of(
            KeiyoushiAquaMangaParserHarnessTest::class.java.protectionDomain.codeSource.location.toURI(),
        )
        check(Files.isDirectory(classRoot)) { "Expected writable unit-test class directory, got: $classRoot" }

        val target = classRoot.resolve("assets/i18n/messages_en.properties")
        Files.createDirectories(target.parent)
        Files.copy(sourceBundle, target, StandardCopyOption.REPLACE_EXISTING)

        check(
            KeiyoushiAquaMangaParserHarnessTest::class.java.classLoader
                ?.getResource("assets/i18n/messages_en.properties") != null,
        ) { "$theme English bundle was not visible to the unit-test classloader" }
    }

    private fun call(name: String, parameterTypes: Array<Class<*>>, vararg args: Any?): Any? {
        val method = findMethod(name, parameterTypes)
        method.isAccessible = true
        return method.invoke(source, *args)
    }

    private fun findMethod(name: String, parameterTypes: Array<Class<*>>): Method {
        var type: Class<*>? = source.javaClass
        while (type != null) {
            try {
                return type.getDeclaredMethod(name, *parameterTypes)
            } catch (_: NoSuchMethodException) {
                type = type.superclass
            }
        }
        error("Method $name not found on ${source.javaClass.name}")
    }

    private fun response(url: String, body: String): Response = Response.Builder()
        .request(Request.Builder().url(url).build())
        .protocol(Protocol.HTTP_1_1)
        .code(200)
        .message("OK")
        .body(body.toResponseBody("text/html; charset=utf-8".toMediaType()))
        .build()
}
