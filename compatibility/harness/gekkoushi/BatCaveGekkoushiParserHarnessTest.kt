package compatibilityfarm

import kotlinx.coroutines.runBlocking
import okhttp3.Request
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.en.BatCave

internal class BatCaveGekkoushiParserHarnessTest {

    @Test
    fun filtersBrowseSearchDetailsChaptersPagesAndDeclaredHeadersUseRealParserCode() = runBlocking {
        val observed = mutableListOf<Request>()
        val context = DeterministicMangaLoaderContext { request ->
            observed += request
            val url = request.url
            assertEquals("batcave.biz", url.host)
            assertEquals("https://batcave.biz/", request.header("Referer"))

            val body = when {
                url.encodedPath == "/comix/" -> """
                    <html><body><script>
                    window.__XFILTER__ = {"filter_items":{"g":{"values":[{"value":"Action","id":9}]}}};
                    </script></body></html>
                """.trimIndent()

                url.encodedPath == "/ComicList/sort" -> listHtml()

                url.encodedPath == "/search/Fixture" -> listHtml()

                url.encodedPath == "/comics/bat-fixture" -> """
                    <html><body>
                      <div class="page__text full-text clearfix">Bat Gekkoushi deterministic description.</div>
                      <ul>
                        <li>Publisher: Fixture Publisher</li>
                        <li>Release type: Ongoing</li>
                      </ul>
                      <a href="/genres/action/">Action</a>
                      <script>
                      window.__DATA__ = {"news_id":77,"chapters":[{"id":1,"title":"Chapter 1","posi":1.0,"date":"01.01.2026"}]};
                      </script>
                    </body></html>
                """.trimIndent()

                url.encodedPath == "/reader/77/1" -> """
                    <html><body><script>
                    window.__DATA__ = {"images":["https://cdn.bat.test/001.jpg","https://cdn.bat.test/002.jpg"]};
                    </script></body></html>
                """.trimIndent()

                else -> error("Unexpected Gekkoushi BatCave request: ${request.method} $url")
            }
            FixtureResponse(body = body)
        }
        val parser = BatCave(context)

        val options = parser.getFilterOptions()
        assertEquals(1, options.availableTags.size)
        assertEquals("9", options.availableTags.single().key)
        assertEquals("Action", options.availableTags.single().title)

        val browse = parser.getList(
            offset = 0,
            order = SortOrder.UPDATED,
            filter = MangaListFilter(),
        )
        assertEquals(1, browse.size)
        assertEquals("Bat Fixture", browse.single().title)
        assertEquals("/comics/bat-fixture", browse.single().url)

        val search = parser.getList(
            offset = 0,
            order = SortOrder.UPDATED,
            filter = MangaListFilter(query = "Fixture"),
        )
        assertEquals(1, search.size)

        val details = parser.getDetails(browse.single())
        assertEquals("Bat Gekkoushi deterministic description.", details.description)
        assertEquals("Fixture Publisher", details.authors.single())
        assertTrue(details.tags.any { it.title == "Action" })

        val chapters = requireNotNull(details.chapters)
        assertEquals(1, chapters.size)
        assertEquals("Chapter 1", chapters.single().title)
        assertEquals("/reader/77/1", chapters.single().url)
        assertEquals(1f, chapters.single().number)

        val pages = parser.getPages(chapters.single())
        assertEquals(2, pages.size)
        assertEquals("https://cdn.bat.test/001.jpg", pages[0].url)
        assertEquals("https://cdn.bat.test/002.jpg", pages[1].url)

        assertTrue(observed.isNotEmpty())
        assertTrue(observed.all { it.header("Referer") == "https://batcave.biz/" })
    }

    private fun listHtml(): String = """
        <html><body>
          <div class="readed d-flex short">
            <a class="readed__img img-fit-cover anim" href="https://batcave.biz/comics/bat-fixture">
              <img data-src="https://cdn.bat.test/cover.jpg">
            </a>
            <h2 class="readed__title"><a href="https://batcave.biz/comics/bat-fixture">Bat Fixture</a></h2>
          </div>
        </body></html>
    """.trimIndent()
}
