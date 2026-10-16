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
import java.util.Calendar

class KeiyoushiKomikuParserHarnessTest {
    private val source: Any by lazy {
        val generated = Class.forName("keiyoushi.source.Generated")
        generated.getDeclaredConstructor().apply { isAccessible = true }.newInstance()
    }

    @Test
    fun executesPinnedKomikuParserAgainstDeterministicResponses() {
        System.getProperty("compatibility.candidate")?.let {
            assertEquals("Unexpected Komiku API generation for the pinned revision", it.toBoolean(), source is KeiSource)
        }
        if (source is KeiSource) {
            executeCoroutineKomiku(source as KeiSource)
            return
        }
        val popularRequest = call(
            "popularMangaRequest",
            arrayOf(Int::class.javaPrimitiveType!!),
            1,
        ) as Request
        assertEquals("api.komiku.org", popularRequest.url.host)
        assertEquals("meta_value_num", popularRequest.url.queryParameter("orderby"))

        val searchRequest = call(
            "searchMangaRequest",
            arrayOf(Int::class.javaPrimitiveType!!, String::class.java, FilterList::class.java),
            1,
            "Alpha",
            FilterList(),
        ) as Request
        assertEquals("Alpha", searchRequest.url.queryParameter("s"))

        val popular = call(
            "popularMangaParse",
            arrayOf(Response::class.java),
            response("https://api.komiku.org/manga/", fixture("komiku/list.html")),
        ) as MangasPage
        assertFalse(popular.hasNextPage)
        assertEquals(1, popular.mangas.size)
        val manga = popular.mangas.single()
        assertEquals("Alpha", manga.title)
        assertEquals("/manga/alpha", manga.url)
        assertEquals("https://thumbnail.komiku.org/alpha.jpg", manga.thumbnail_url)

        val detailsRequest = call(
            "mangaDetailsRequest",
            arrayOf(SManga::class.java),
            manga,
        ) as Request
        assertEquals("https://komiku.org/manga/alpha", detailsRequest.url.toString())

        val details = call(
            "mangaDetailsParse",
            arrayOf(Response::class.java),
            response(detailsRequest.url.toString(), fixture("komiku/details.html")),
        ) as SManga
        assertTrue(details.description.orEmpty().contains("Alpha synopsis"))
        assertEquals("Author A", details.author)
        assertEquals("Action", details.genre)
        assertEquals(SManga.ONGOING, details.status)
        assertEquals("https://thumbnail.komiku.org/alpha.jpg", details.thumbnail_url)

        val chapterRequest = call(
            "chapterListRequest",
            arrayOf(SManga::class.java),
            manga,
        ) as Request
        val chapters = call(
            "chapterListParse",
            arrayOf(Response::class.java),
            response(chapterRequest.url.toString(), fixture("komiku/details.html")),
        ) as List<*>
        assertEquals(1, chapters.size)
        val chapter = chapters.single() as SChapter
        assertEquals("Chapter 1", chapter.name)
        assertEquals("/alpha-chapter-1/", chapter.url)
        assertTrue(chapter.date_upload > 0L)

        val pageRequest = call(
            "pageListRequest",
            arrayOf(SChapter::class.java),
            chapter,
        ) as Request
        assertEquals("https://komiku.org/alpha-chapter-1/", pageRequest.url.toString())

        val pages = call(
            "pageListParse",
            arrayOf(Response::class.java),
            response(pageRequest.url.toString(), fixture("komiku/pages.html")),
        ) as List<*>
        assertEquals(2, pages.size)
        val firstPage = pages.first() as Page
        assertEquals("https://img.komiku.org/001.jpg", firstPage.imageUrl)
        assertEquals(pageRequest.url.toString(), firstPage.url)

        val imageRequest = call(
            "imageRequest",
            arrayOf(Page::class.java),
            firstPage,
        ) as Request
        assertEquals(firstPage.imageUrl, imageRequest.url.toString())
        assertEquals(firstPage.url, imageRequest.header("Referer"))
        assertNotNull(imageRequest.header("Referer"))
    }

    private fun executeCoroutineKomiku(parser: KeiSource) = runBlocking {
        assertEquals("Komiku", parser.name)
        assertEquals("id", parser.lang)
        assertEquals("https://komiku.org", parser.baseUrl)
        val observed = mutableListOf<Request>()
        DeterministicNetwork.install { request ->
            observed += request
            val url = request.url
            check(request.method == "GET" && url.host in setOf("api.komiku.org", "komiku.org"))
            when {
                url.host == "api.komiku.org" && url.encodedPath in setOf("/other/hot/", "/other/hot/page/2/", "/manga") ->
                    FixtureResponse(fixture("komiku/list.html"))
                url.encodedPath == "/manga/alpha" -> FixtureResponse(fixture("komiku/details.html"))
                url.encodedPath == "/manga/expanded" -> FixtureResponse(
                    fixture("komiku/details.html")
                        .replace("<div id=\"Sinopsis\"><p>Alpha synopsis</p></div>", "<p class=\"desc\" itemprop=\"description\">Expanded synopsis</p>")
                        .replace("Judul Indonesia", "Judul Alternatif")
                        .replace("Pengarang", "Author")
                        .replace("<div class=\"ims\"><img", "<div><img itemprop=\"image\""),
                )
                url.encodedPath == "/alpha-chapter-1/" -> FixtureResponse(
                    fixture("komiku/pages.html").replace("</div>", "<img src=\"https://img.komiku.org/komiku-promosi.jpg\"></div>"),
                )
                else -> error("Unexpected Komiku request: $url")
            }
        }
        try {
            val popular = parser.getPopularManga(1)
            assertFalse(popular.hasNextPage)
            assertEquals(1, popular.mangas.size)
            val manga = popular.mangas.single()
            assertEquals("Alpha", manga.title)
            assertEquals("/manga/alpha", manga.url)
            assertEquals("https://thumbnail.komiku.org/alpha.jpg", manga.thumbnail_url)
            parser.getPopularManga(2)
            parser.getLatestUpdates(1)
            assertEquals("Alpha", parser.getSearchMangaList(1, "Alpha", FilterList()).mangas.single().title)
            val update = parser.getMangaUpdate(manga, emptyList(), true, true)
            val details = update.manga
            assertTrue(details.description.orEmpty().contains("Alpha synopsis"))
            assertTrue(details.description.orEmpty().contains("Alpha Indonesia"))
            assertEquals("Author A", details.author)
            assertEquals("Action", details.genre)
            assertEquals(SManga.ONGOING, details.status)
            assertEquals("https://thumbnail.komiku.org/alpha.jpg", details.thumbnail_url)
            assertEquals(1, update.chapters.size)
            val chapter = update.chapters.single()
            assertEquals("Chapter 1", chapter.name)
            assertEquals("/alpha-chapter-1/", chapter.url)
            assertTrue(chapter.date_upload > 0L)
            val pages = parser.getPageList(chapter)
            assertEquals(2, pages.size)
            assertEquals(listOf(0, 1), pages.map { it.index })
            assertEquals(listOf("https://img.komiku.org/001.jpg", "https://img.komiku.org/002.jpg"), pages.map { it.imageUrl })
            val image = call("imageRequest", arrayOf(Page::class.java), pages.first()) as Request
            assertEquals(pages.first().imageUrl, image.url.toString())
            assertEquals("https://komiku.org/alpha-chapter-1/", image.header("Referer"))

            val expanded = parser.getMangaUpdate(SManga.create().apply { url = "/manga/expanded" }, emptyList(), true, true).manga
            assertTrue(expanded.description.orEmpty().contains("Expanded synopsis"))
            assertTrue(expanded.description.orEmpty().contains("Judul Alternatif: Alpha Indonesia"))
            assertEquals("Author A", expanded.author)
            assertEquals("https://thumbnail.komiku.org/alpha.jpg", expanded.thumbnail_url)
            assertEquals(0L, call("parseRelativeDate", arrayOf(String::class.java), "invalid lalu"))
            val earliest = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, -2) }.timeInMillis
            val relative = call("parseRelativeDate", arrayOf(String::class.java), "2 hari lalu") as Long
            val latest = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, -2) }.timeInMillis
            assertTrue("Relative date must subtract two days", relative in earliest..latest)
            assertTrue(observed.any { it.url.encodedPath == "/other/hot/" && it.url.queryParameter("orderby") == "meta_value_num" })
            assertTrue(observed.any { it.url.encodedPath == "/other/hot/page/2/" })
            assertTrue(observed.any { it.url.encodedPath == "/manga" && it.url.queryParameter("orderby") == "modified" })
            assertTrue(observed.any { it.url.encodedPath == "/manga" && it.url.queryParameter("s") == "Alpha" })
        } finally {
            DeterministicNetwork.clear()
        }
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

    private fun fixture(path: String): String =
        requireNotNull(javaClass.classLoader.getResource("compatibility-farm/$path")) {
            "Fixture not found: $path"
        }.readText()

    private fun response(url: String, body: String): Response = Response.Builder()
        .request(Request.Builder().url(url).build())
        .protocol(Protocol.HTTP_1_1)
        .code(200)
        .message("OK")
        .body(body.toResponseBody("text/html; charset=utf-8".toMediaType()))
        .build()
}
