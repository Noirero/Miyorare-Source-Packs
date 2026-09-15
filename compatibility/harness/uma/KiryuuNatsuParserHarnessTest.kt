package compatibilityfarm

import java.util.Collections
import kotlinx.coroutines.runBlocking
import okhttp3.Request
import okio.Buffer
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.id.Kiryuu

/**
 * Real-parser deterministic coverage for the Natsu adapter family.
 *
 * The fixtures stay inline because this test is meant to exercise request choreography,
 * parser behavior and headers rather than maintain a second copy of a live site's HTML.
 */
internal class KiryuuNatsuParserHarnessTest {

    private val nonceHtml = """
        <!doctype html><html><body>
        <input name="search_nonce" value="fixture-nonce">
        </body></html>
    """.trimIndent()

    private val searchHtml = """
        <!doctype html><html><body>
        <div>
          <a href="https://v7.kiryuu.to/manga/sample-kiryuu/">
            <img src="https://v7.kiryuu.to/media/search-cover.jpg">
          </a>
        </div>
        </body></html>
    """.trimIndent()

    private val listJson = """
        [
          {
            "slug": "sample-kiryuu",
            "title": {"rendered": "Fixture Kiryuu"},
            "_embedded": {
              "wp:featuredmedia": [
                {"source_url": "https://v7.kiryuu.to/media/cover.jpg"}
              ]
            }
          }
        ]
    """.trimIndent()

    private val idJson = """
        [{"id": 101, "slug": "sample-kiryuu"}]
    """.trimIndent()

    private val detailsJson = """
        {
          "id": 101,
          "slug": "sample-kiryuu",
          "title": {"rendered": "Fixture Kiryuu Detailed"},
          "content": {"rendered": "<p>Fixture Kiryuu description.</p>"},
          "_embedded": {
            "wp:featuredmedia": [
              {"source_url": "https://v7.kiryuu.to/media/cover-detail.jpg"}
            ],
            "wp:term": [
              [{"taxonomy": "genre", "name": "Action"}],
              [{"taxonomy": "type", "name": "Manga"}],
              [{"taxonomy": "status", "name": "Ongoing"}],
              [{"taxonomy": "series-author", "name": "Fixture Author"}]
            ]
          }
        }
    """.trimIndent()

    private val altTitleHtml = """
        <!doctype html><html><body>
        <h1 itemprop="name">Fixture Kiryuu Detailed</h1>
        <div>Fixture Alternate, Another Alternate</div>
        </body></html>
    """.trimIndent()

    private val chaptersHtml = """
        <!doctype html><html><body>
        <div id="chapter-list">
          <div data-chapter-number="1">
            <a href="https://v7.kiryuu.to/manga/sample-kiryuu/chapter-1/">
              <div class="font-medium"><span>Chapter 1</span></div>
              <time datetime="2026-01-01T00:00:00Z"></time>
            </a>
          </div>
        </div>
        </body></html>
    """.trimIndent()

    private val emptyChaptersHtml = """
        <!doctype html><html><body><div id="chapter-list"></div></body></html>
    """.trimIndent()

    private val pagesHtml = """
        <!doctype html><html><body>
        <main>
          <div class="relative">
            <section>
              <img src="https://v7.kiryuu.to/media/chapter-1/001.jpg">
              <img src="https://v7.kiryuu.to/media/chapter-1/002.jpg">
            </section>
          </div>
        </main>
        </body></html>
    """.trimIndent()

    @Test
    fun nonceMultipartRestDetailsHtmxChaptersAndPagesUseRealNatsuParserCode() = runBlocking {
        val observed = Collections.synchronizedList(mutableListOf<Request>())
        val multipartBodies = Collections.synchronizedList(mutableListOf<String>())

        val context = DeterministicMangaLoaderContext { request: Request ->
            observed += request
            val url = request.url

            if (request.method == "POST") {
                val buffer = Buffer()
                request.body?.writeTo(buffer)
                multipartBodies += buffer.readUtf8()
            }

            when {
                url.host == "v7.kiryuu.to" &&
                    url.encodedPath == "/wp-admin/admin-ajax.php" &&
                    url.queryParameter("type") == "search_form" &&
                    url.queryParameter("action") == "get_nonce" ->
                    FixtureResponse(nonceHtml)

                url.host == "v7.kiryuu.to" &&
                    request.method == "POST" &&
                    url.encodedPath == "/wp-admin/admin-ajax.php" &&
                    url.queryParameter("action") == "advanced_search" ->
                    FixtureResponse(searchHtml)

                url.host == "v7.kiryuu.to" &&
                    url.encodedPath == "/wp-json/wp/v2/manga" &&
                    url.queryParameter("slug[]") == "sample-kiryuu" ->
                    FixtureResponse(listJson, contentType = "application/json; charset=utf-8")

                url.host == "v7.kiryuu.to" &&
                    url.encodedPath == "/wp-json/wp/v2/manga" &&
                    url.queryParameter("slug") == "sample-kiryuu" ->
                    FixtureResponse(idJson, contentType = "application/json; charset=utf-8")

                url.host == "v7.kiryuu.to" &&
                    url.encodedPath == "/wp-json/wp/v2/manga/101" ->
                    FixtureResponse(detailsJson, contentType = "application/json; charset=utf-8")

                url.host == "v7.kiryuu.to" &&
                    url.encodedPath == "/manga/sample-kiryuu/" ->
                    FixtureResponse(altTitleHtml)

                url.host == "v7.kiryuu.to" &&
                    url.encodedPath == "/wp-admin/admin-ajax.php" &&
                    url.queryParameter("action") == "chapter_list" &&
                    url.queryParameter("page") == "1" ->
                    FixtureResponse(chaptersHtml)

                url.host == "v7.kiryuu.to" &&
                    url.encodedPath == "/wp-admin/admin-ajax.php" &&
                    url.queryParameter("action") == "chapter_list" &&
                    url.queryParameter("page") == "2" ->
                    FixtureResponse(emptyChaptersHtml)

                url.host == "v7.kiryuu.to" &&
                    url.encodedPath == "/manga/sample-kiryuu/chapter-1/" ->
                    FixtureResponse(pagesHtml)

                else -> error("Unexpected Kiryuu/Natsu parser request: ${request.method} $url")
            }
        }

        val parser = Kiryuu(context)

        val browse = parser.getList(
            offset = 0,
            order = SortOrder.UPDATED,
            filter = MangaListFilter(),
        )
        assertEquals(1, browse.size)
        assertEquals("Fixture Kiryuu", browse.single().title)
        assertEquals("/manga/sample-kiryuu", browse.single().url)
        assertTrue(browse.single().coverUrl.orEmpty().endsWith("/media/cover.jpg"))

        val search = parser.getList(
            offset = 0,
            order = SortOrder.RELEVANCE,
            filter = MangaListFilter(query = "Fixture Search"),
        )
        assertEquals(1, search.size)
        assertEquals("Fixture Kiryuu", search.single().title)
        assertTrue(multipartBodies.any { it.contains("Fixture Search") })

        val details = parser.getDetails(browse.single())
        assertEquals("Fixture Kiryuu Detailed", details.title)
        assertEquals("Fixture Kiryuu description.", details.description)
        assertEquals("Fixture Author", details.authors.single())
        assertTrue(details.altTitles.contains("Fixture Alternate"))
        assertNotNull(details.state)
        assertTrue(details.tags.any { it.title == "Action" })

        val chapters = requireNotNull(details.chapters)
        assertEquals(1, chapters.size)
        assertEquals("Chapter 1", chapters.single().title)
        assertEquals(1f, chapters.single().number)
        assertTrue(chapters.single().url.endsWith("/manga/sample-kiryuu/chapter-1/"))

        val pages = parser.getPages(chapters.single())
        assertEquals(2, pages.size)
        assertTrue(pages[0].url.endsWith("/media/chapter-1/001.jpg"))
        assertTrue(pages[1].url.endsWith("/media/chapter-1/002.jpg"))

        val advancedSearch = observed.filter {
            it.method == "POST" &&
                it.url.encodedPath == "/wp-admin/admin-ajax.php" &&
                it.url.queryParameter("action") == "advanced_search"
        }
        assertEquals(2, advancedSearch.size)
        assertTrue(advancedSearch.all { it.header("Origin") == "https://v7.kiryuu.to" })
        assertTrue(advancedSearch.all { it.header("Referer") == "https://v7.kiryuu.to/advanced-search/" })

        val chapterRequest = observed.first {
            it.url.encodedPath == "/wp-admin/admin-ajax.php" &&
                it.url.queryParameter("action") == "chapter_list" &&
                it.url.queryParameter("page") == "1"
        }
        assertEquals("true", chapterRequest.header("HX-Request"))
        assertEquals("chapter-list", chapterRequest.header("HX-Target"))
        assertEquals("chapter-list", chapterRequest.header("HX-Trigger"))
        assertEquals(
            "https://v7.kiryuu.to/manga/sample-kiryuu/",
            chapterRequest.header("HX-Current-URL"),
        )
        assertEquals(
            "https://v7.kiryuu.to/manga/sample-kiryuu/",
            chapterRequest.header("Referer"),
        )
    }
}
