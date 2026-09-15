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

class KeiyoushiKomikuParserHarnessTest {
    private val source: Any by lazy {
        val generated = Class.forName("keiyoushi.source.Generated")
        generated.getDeclaredConstructor().apply { isAccessible = true }.newInstance()
    }

    @Test
    fun executesPinnedKomikuParserAgainstDeterministicResponses() {
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
