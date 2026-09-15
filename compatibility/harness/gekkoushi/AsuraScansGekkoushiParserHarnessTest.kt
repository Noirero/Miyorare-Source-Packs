package compatibilityfarm

import kotlinx.coroutines.runBlocking
import okhttp3.Request
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.en.AsuraScansParser

internal class AsuraScansGekkoushiParserHarnessTest {

    @Test
    fun tagsBrowseSearchDetailsChaptersAndAstroPagesUseRealParserCode() = runBlocking {
        val observed = mutableListOf<Request>()
        val context = DeterministicMangaLoaderContext { request ->
            observed += request
            val url = request.url
            val body = when {
                url.host == "api.asurascans.com" && url.encodedPath == "/api/genres" ->
                    """{"data":[{"name":"Action","slug":"action"}]}"""

                url.host == "asurascans.com" && url.encodedPath == "/browse" -> {
                    assertEquals("1", url.queryParameter("page"))
                    listHtml()
                }

                url.host == "asurascans.com" && url.encodedPath == "/comics/asura-fixture-abc" -> detailsHtml()

                url.host == "asurascans.com" && url.encodedPath == "/comics/asura-fixture-abc/chapter/1" -> pagesHtml()

                else -> error("Unexpected Gekkoushi Asura request: ${request.method} $url")
            }
            FixtureResponse(
                body = body,
                contentType = if (url.host.startsWith("api.")) "application/json; charset=utf-8" else "text/html; charset=utf-8",
            )
        }
        val parser = AsuraScansParser(context)

        val options = parser.getFilterOptions()
        assertEquals(1, options.availableTags.size)
        assertEquals("action", options.availableTags.single().key)

        val browse = parser.getList(
            offset = 0,
            order = SortOrder.UPDATED,
            filter = MangaListFilter(),
        )
        assertEquals(1, browse.size)
        assertEquals("Asura Fixture", browse.single().title)
        assertEquals("/comics/asura-fixture-abc", browse.single().url)

        val search = parser.getList(
            offset = 0,
            order = SortOrder.RATING,
            filter = MangaListFilter(query = "Fixture"),
        )
        assertEquals(1, search.size)
        assertTrue(observed.any {
            it.url.encodedPath == "/browse" &&
                it.url.queryParameter("q") == "Fixture" &&
                it.url.queryParameter("sort") == "rating"
        })

        val details = parser.getDetails(browse.single())
        assertEquals("Asura deterministic description.", details.description)
        assertEquals("Fixture Author", details.authors.single())
        assertTrue(details.tags.any { it.title == "Action" })
        assertEquals(4.5f, details.rating)

        val chapters = requireNotNull(details.chapters)
        assertEquals(1, chapters.size)
        assertEquals("Chapter 1", chapters.single().title)
        assertEquals(1f, chapters.single().number)
        assertEquals("https://asurascans.com/comics/asura-fixture-abc/chapter/1", chapters.single().url)
        assertTrue(chapters.single().uploadDate > 0L)

        val pages = parser.getPages(chapters.single())
        assertEquals(2, pages.size)
        assertEquals("https://cdn.asura.test/001.jpg", pages[0].url)
        assertEquals("https://cdn.asura.test/002.jpg", pages[1].url)
    }

    private fun listHtml(): String = """
        <html><body>
          <div id="series-grid">
            <div class="series-card">
              <a href="/comics/asura-fixture-abc">
                <img src="https://cdn.asura.test/cover.jpg">
                <div><span>45</span></div>
              </a>
              <h3>Asura Fixture</h3>
              <span class="capitalize">Ongoing</span>
            </div>
          </div>
        </body></html>
    """.trimIndent()

    private fun detailsHtml(): String = """
        <html><body>
          <div id="description-text">Asura deterministic description.</div>
          <astro-island component-url="/components/DescriptionModal.js"
            props='{"genres":[0,[[0,{"name":[0,"Action"]}]]],"author":[0,"Fixture Author"],"status":[0,"ongoing"],"rating":[0,45.0]}'>
          </astro-island>
          <astro-island component-url="/components/ChapterList.js"
            props='{"chapters":[0,[[0,{"number":[0,"1"],"published_at":[0,"2026-01-01T00:00:00Z"]}]]]}'>
          </astro-island>
          <div class="divide-y">
            <a href="/comics/asura-fixture-abc/chapter/1"><span class="block">Chapter 1</span></a>
          </div>
        </body></html>
    """.trimIndent()

    private fun pagesHtml(): String = """
        <html><body>
          <astro-island component-url="/components/ChapterReader.js"
            props='{"pages":[0,[[0,{"url":[0,"https://cdn.asura.test/001.jpg"]}],[1,{"url":[0,"https://cdn.asura.test/002.jpg"]}]]]}'></astro-island>
        </body></html>
    """.trimIndent()
}
