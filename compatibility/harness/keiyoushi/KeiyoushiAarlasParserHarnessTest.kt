package compatibilityfarm

import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.jsoup.Jsoup
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.lang.reflect.Method

class KeiyoushiAarlasParserHarnessTest {
    private val source: Any by lazy {
        val generated = Class.forName("keiyoushi.source.Generated")
        generated.getDeclaredConstructor().apply { isAccessible = true }.newInstance()
    }

    @Test
    fun executesPinnedAarlasZeistMangaParserAgainstDeterministicResponses() {
        assertTrue(source.javaClass.superclass.name.contains("aarlas", ignoreCase = true))
        assertTrue(
            generateSequence<Class<*>>(source.javaClass) { it.superclass }
                .any { it.name.endsWith(".ZeistManga") },
        )

        val popularUrl = call(
            "popularMangaUrl",
            arrayOf(Int::class.javaPrimitiveType!!),
            1,
        ) as String
        assertEquals("https://www.arlas.online", popularUrl)

        val popular = call(
            "parsePopularManga",
            arrayOf(Response::class.java),
            response(
                popularUrl,
                """
                <div class="PopularPosts">
                  <div class="grid">
                    <figure>
                      <img src="/covers/fixture.jpg" />
                      <figcaption>
                        <a href="https://www.arlas.online/2026/01/fixture-series.html">Fixture Series</a>
                      </figcaption>
                    </figure>
                  </div>
                </div>
                """.trimIndent(),
                "text/html; charset=utf-8",
            ),
        ) as MangasPage
        assertFalse(popular.hasNextPage)
        assertEquals(1, popular.mangas.size)
        assertEquals("Fixture Series", popular.mangas.single().title)
        assertEquals("/2026/01/fixture-series.html", popular.mangas.single().url)
        assertEquals("https://www.arlas.online/covers/fixture.jpg", popular.mangas.single().thumbnail_url)

        val search = call(
            "parseSearchManga",
            arrayOf(Response::class.java),
            response(
                "https://www.arlas.online/feeds/posts/default/-/Series?alt=json",
                """
                {
                  "feed": {
                    "entry": [
                      {
                        "title": {"${'$'}t": "Fixture Search Result"},
                        "category": [{"term": "Series"}],
                        "link": [
                          {
                            "rel": "alternate",
                            "href": "https://www.arlas.online/2026/02/search-result.html"
                          }
                        ],
                        "content": {
                          "${'$'}t": "<p><img src='https://www.arlas.online/covers/search.jpg' /></p>"
                        }
                      }
                    ]
                  }
                }
                """.trimIndent(),
                "application/json; charset=utf-8",
            ),
        ) as MangasPage
        assertFalse(search.hasNextPage)
        assertEquals(1, search.mangas.size)
        assertEquals("Fixture Search Result", search.mangas.single().title)
        assertEquals("/2026/02/search-result.html", search.mangas.single().url)
        assertEquals("https://www.arlas.online/covers/search.jpg", search.mangas.single().thumbnail_url)

        val feedDocument = Jsoup.parse(
            """
            <div id="clwd"><script>clwd.run('Fixture Series')</script></div>
            """.trimIndent(),
            "https://www.arlas.online/2026/01/fixture-series.html",
        )
        val chapterFeed = call(
            "getChapterFeedUrl",
            arrayOf(org.jsoup.nodes.Document::class.java, String::class.java),
            feedDocument,
            "Fixture Series",
        ) as String
        assertTrue(chapterFeed.startsWith("https://www.arlas.online/feeds/posts/default/-/Chapter/"))
        assertTrue(chapterFeed.contains("Fixture"))
        assertTrue(chapterFeed.contains("alt=json"))

        val pages = call(
            "pageListParse",
            arrayOf(org.jsoup.nodes.Document::class.java),
            Jsoup.parse(
                """
                <div class="check-box">
                  <div class="separator"><img src="/pages/001.jpg" /></div>
                  <div class="separator"><img src="/pages/002.jpg" /></div>
                </div>
                """.trimIndent(),
                "https://www.arlas.online/2026/01/chapter-1.html",
            ),
        ) as List<*>
        assertEquals(2, pages.size)
        assertEquals("https://www.arlas.online/pages/001.jpg", (pages[0] as Page).imageUrl)
        assertEquals("https://www.arlas.online/pages/002.jpg", (pages[1] as Page).imageUrl)

        val preferUpdated = call("getPreferChapterUpdatedDate", emptyArray()) as Boolean
        assertTrue(preferUpdated)
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

    private fun response(url: String, body: String, mediaType: String): Response = Response.Builder()
        .request(Request.Builder().url(url).build())
        .protocol(Protocol.HTTP_1_1)
        .code(200)
        .message("OK")
        .body(body.toResponseBody(mediaType.toMediaType()))
        .build()
}
