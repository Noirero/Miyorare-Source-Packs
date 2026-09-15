package compatibilityfarm

import java.util.Collections
import kotlinx.coroutines.runBlocking
import okhttp3.Request
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.en.AquaReader

/** Deterministic real-parser coverage for AquaReader's Madara family path. */
internal class AquaReaderMadaraParserHarnessTest {

    private val listHtml = """
        <!doctype html><html><body>
        <div class="row c-tabs-item__content">
          <a href="https://aquareader.org/series/aqua-fixture/">
            <img src="https://aquareader.org/media/aqua-list.jpg">
          </a>
          <div class="item-summary">
            <h3>Fixture Aqua</h3>
            <div class="mg_author"><a>Fixture List Author</a></div>
            <div class="mg_genres"><a href="https://aquareader.org/manga-genre/action/">Action</a></div>
            <div class="mg_status"><div class="summary-content">ongoing</div></div>
          </div>
        </div>
        </body></html>
    """.trimIndent()

    private val detailsHtml = """
        <!doctype html><html><body>
        <h1 class="aqua-series-info__title">Fixture Aqua Detailed</h1>
        <img class="aqua-series-cover__img" src="https://aquareader.org/media/aqua-detail.jpg">
        <div class="aqua-series-synopsis"><p>Fixture Aqua synopsis.</p></div>
        <div class="aqua-series-meta__status">Ongoing</div>
        <span class="aqua-series-genre-pill">Action</span>
        <div class="aqua-series-info__creator-value"><a>Fixture Aqua Author</a></div>
        <div class="aqua-ch-item">
          <a href="https://aquareader.org/series/aqua-fixture/chapter-1/">
            <span class="aqua-ch-item__name">Chapter 1</span>
          </a>
          <span class="aqua-ch-item__time">Jan 1, 2026</span>
        </div>
        </body></html>
    """.trimIndent()

    private val pagesHtml = """
        <!doctype html><html><body>
        <div class="main-col-inner">
          <div class="reading-content">
            <div class="page-break"><img src="https://aquareader.org/media/aqua-001.jpg"></div>
            <div class="page-break"><img src="https://aquareader.org/media/aqua-002.jpg"></div>
          </div>
        </div>
        </body></html>
    """.trimIndent()

    @Test
    fun browseSearchDetailsChaptersAndPagesUseRealMadaraCode() = runBlocking {
        val observed = Collections.synchronizedList(mutableListOf<Request>())
        val context = DeterministicMangaLoaderContext { request: Request ->
            observed += request
            val url = request.url
            when {
                url.host == "aquareader.org" &&
                    url.encodedPath == "/" &&
                    url.queryParameter("post_type") == "wp-manga" ->
                    FixtureResponse(listHtml)

                url.host == "aquareader.org" &&
                    url.encodedPath == "/series/aqua-fixture/" ->
                    FixtureResponse(detailsHtml)

                url.host == "aquareader.org" &&
                    url.encodedPath == "/series/aqua-fixture/chapter-1/" ->
                    FixtureResponse(pagesHtml)

                else -> error("Unexpected AquaReader/Madara request: ${request.method} $url")
            }
        }

        val parser = AquaReader(context)

        val browse = parser.getList(
            offset = 0,
            order = SortOrder.UPDATED,
            filter = MangaListFilter(),
        )
        assertEquals(1, browse.size)
        assertEquals("Fixture Aqua", browse.single().title)
        assertTrue(browse.single().url.endsWith("/series/aqua-fixture/"))
        assertEquals("Fixture List Author", browse.single().authors.single())

        val search = parser.getList(
            offset = 0,
            order = SortOrder.RELEVANCE,
            filter = MangaListFilter(query = "Fixture Aqua"),
        )
        assertEquals(1, search.size)
        assertEquals("Fixture Aqua", search.single().title)
        assertTrue(
            observed.any {
                it.url.encodedPath == "/" &&
                    it.url.queryParameter("s") == "Fixture Aqua" &&
                    it.url.queryParameter("post_type") == "wp-manga"
            },
        )

        val details = parser.getDetails(browse.single())
        assertEquals("Fixture Aqua Detailed", details.title)
        assertTrue(details.coverUrl.orEmpty().endsWith("/media/aqua-detail.jpg"))
        assertTrue(details.description.orEmpty().contains("Fixture Aqua synopsis."))
        assertEquals("Fixture Aqua Author", details.authors.single())
        assertTrue(details.tags.any { it.title == "Action" })
        assertNotNull(details.state)

        val chapters = requireNotNull(details.chapters)
        assertEquals(1, chapters.size)
        assertEquals("Chapter 1", chapters.single().title)
        assertEquals(1f, chapters.single().number)
        assertTrue(chapters.single().url.endsWith("/series/aqua-fixture/chapter-1/"))

        val pages = parser.getPages(chapters.single())
        assertEquals(2, pages.size)
        assertTrue(pages[0].url.endsWith("/media/aqua-001.jpg"))
        assertTrue(pages[1].url.endsWith("/media/aqua-002.jpg"))

        assertTrue(observed.isNotEmpty())
        assertTrue(observed.all { it.url.host == "aquareader.org" })
        assertTrue(
            observed.any {
                it.url.encodedPath == "/" &&
                    it.url.queryParameter("m_orderby") == "latest"
            },
        )
    }
}
