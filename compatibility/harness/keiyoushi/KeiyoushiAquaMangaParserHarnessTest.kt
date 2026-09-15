package compatibilityfarm

import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
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

class KeiyoushiAquaMangaParserHarnessTest {
    private val source: Any by lazy {
        val generated = Class.forName("keiyoushi.source.Generated")
        generated.getDeclaredConstructor().apply { isAccessible = true }.newInstance()
    }

    @Test
    fun executesPinnedAquaMadaraLegacyParserAgainstDeterministicResponses() {
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
