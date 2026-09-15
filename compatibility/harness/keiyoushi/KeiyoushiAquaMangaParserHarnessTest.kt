package compatibilityfarm

import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.junit.Assert.assertEquals
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
    fun executesPinnedAquaMadaraParserAgainstDeterministicDocuments() {
        assertEquals(".aqua-archive-card", call("popularMangaSelector", emptyArray()))
        assertEquals("a.next", call("popularMangaNextPageSelector", emptyArray()))
        assertEquals(".aqua-series-info__title", call("getMangaDetailsSelectorTitle", emptyArray()))
        assertEquals(".aqua-ch-item", call("chapterListSelector", emptyArray()))

        val archive = document(
            "https://aquareader.org/manga/",
            """
            <div class="page-item-detail" data-post-id="123">
              <div class="post-title"><a href="https://aquareader.org/manga/alpha/">Alpha Aqua</a></div>
              <img src="https://aquareader.org/covers/alpha.jpg" />
            </div>
            """.trimIndent(),
        )
        val mangas = call(
            "parseArchive",
            arrayOf(Document::class.java),
            archive,
        ) as List<*>
        assertEquals(1, mangas.size)
        val manga = mangas.single() as SManga
        assertEquals("Alpha Aqua", manga.title)
        assertEquals("123", manga.url)
        assertEquals("https://aquareader.org/covers/alpha.jpg", manga.thumbnail_url)

        val details = call(
            "parseDetails",
            arrayOf(Document::class.java, String::class.java, String::class.java),
            document(
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
            "123",
            null,
        ) as SManga
        assertEquals("Alpha Aqua", details.title)
        assertEquals("Fixture Author", details.author)
        assertEquals("Fixture Author", details.artist)
        assertEquals("Fixture Aqua synopsis.", details.description)
        assertEquals("Action", details.genre)
        assertEquals(SManga.ONGOING, details.status)
        assertEquals("https://aquareader.org/covers/alpha.jpg", details.thumbnail_url)

        val chapters = call(
            "parseChapterList",
            arrayOf(Document::class.java, String::class.java),
            document(
                "https://aquareader.org/manga/alpha/",
                """
                <a class="aqua-ch-item" href="https://aquareader.org/manga/alpha/chapter-1/">
                  <span class="aqua-ch-item__name">Chapter 1</span>
                </a>
                """.trimIndent(),
            ),
            "/manga/alpha/",
        ) as List<*>
        assertEquals(1, chapters.size)
        val chapter = chapters.single() as SChapter
        assertEquals("Chapter 1", chapter.name)
        assertEquals("https://aquareader.org/manga/alpha/chapter-1/", chapter.url)

        val pages = call(
            "parsePages",
            arrayOf(Document::class.java),
            document(
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
        assertTrue(first.url.endsWith("/manga/alpha/chapter-1/"))
        assertNotNull(second.imageUrl)
    }

    private fun document(baseUrl: String, body: String): Document = Jsoup.parse(body, baseUrl)

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
}
