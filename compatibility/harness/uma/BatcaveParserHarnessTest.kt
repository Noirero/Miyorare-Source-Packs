package compatibilityfarm

import kotlinx.coroutines.runBlocking
import okhttp3.Request
import okio.Buffer
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.en.Batcave

internal class BatcaveParserHarnessTest {

    private fun requestBody(request: Request): String = Buffer().use { buffer ->
        request.body?.writeTo(buffer)
        buffer.readUtf8()
    }

    private fun context(): DeterministicMangaLoaderContext =
        DeterministicMangaLoaderContext { request ->
            assertEquals("batcave.biz", request.url.host)
            val body = when {
                request.url.encodedPath == "/comix" -> """
                    <html><body>
                    <script>window.__XFILTER__ = {"filter_items":{"g":{"values":[{"value":"Action","id":9}]}}};</script>
                    </body></html>
                """.trimIndent()

                request.url.encodedPath.startsWith("/ComicList/") -> {
                    assertEquals("POST", request.method)
                    val form = requestBody(request)
                    assertTrue(form.contains("dlenewssortby=rating"))
                    assertTrue(form.contains("dledirection=desc"))
                    listHtml()
                }

                request.url.encodedPath == "/search/Fixture" -> {
                    assertEquals("GET", request.method)
                    listHtml()
                }

                request.url.encodedPath == "/comics/bat-fixture" -> """
                    <html><body>
                    <header class="page__header"><h1>Bat Fixture Detailed</h1></header>
                    <div class="page__poster"><img src="/covers/bat-detail.jpg"></div>
                    <div class="page__text">Bat deterministic description.</div>
                    <ul class="page__list">
                      <li><div>Writer</div><a>Fixture Writer</a></li>
                      <li><div>Release type</div>Ongoing</li>
                    </ul>
                    <div class="page__tags"><a>Action</a></div>
                    <script>window.__DATA__ = {"news_id":77,"chapters":[{"id":1,"title":"Chapter 1","posi":1.0,"date":"01.01.2026"}]};</script>
                    </body></html>
                """.trimIndent()

                request.url.encodedPath == "/engine/ajax/controller.php" -> {
                    assertEquals("POST", request.method)
                    assertEquals("api", request.url.queryParameter("mod"))
                    assertEquals("reader/getChapterData", request.url.queryParameter("action"))
                    assertEquals("https://batcave.biz/", request.header("Referer"))
                    val json = requestBody(request)
                    assertTrue(json.contains("\"news_id\":\"77\"") || json.contains("\"news_id\":77"))
                    assertTrue(json.contains("\"chapter_id\":\"1\"") || json.contains("\"chapter_id\":1"))
                    """{"data":{"images":["https://cdn.bat.test/001.jpg","/uploads/002.jpg"]}}"""
                }

                else -> error("Unexpected BatCave parser request: ${request.method} ${request.url}")
            }
            FixtureResponse(
                body = body,
                contentType = if (request.url.encodedPath == "/engine/ajax/controller.php") {
                    "application/json; charset=utf-8"
                } else {
                    "text/html; charset=utf-8"
                },
            )
        }

    private fun listHtml(): String = """
        <html><body><div id="dle-content">
          <div class="readed">
            <div class="readed__title"><a href="/comics/bat-fixture">Bat Fixture</a></div>
            <div class="readed__img"><img data-src="/covers/bat.jpg"></div>
          </div>
        </div></body></html>
    """.trimIndent()

    @Test
    fun filterBrowseSearchDetailsChaptersAndReaderApiUseRealParserCode() = runBlocking {
        val parser = Batcave(context())

        val options = parser.getFilterOptions()
        assertEquals(1, options.availableTags.size)
        assertEquals("g_9", options.availableTags.single().key)

        val browse = parser.getList(
            offset = 0,
            order = SortOrder.POPULARITY,
            filter = MangaListFilter(),
        )
        assertEquals(1, browse.size)
        assertEquals("Bat Fixture", browse.single().title)
        assertEquals("/comics/bat-fixture", browse.single().url)

        val search = parser.getList(
            offset = 0,
            order = SortOrder.POPULARITY,
            filter = MangaListFilter(query = "Fixture"),
        )
        assertEquals(1, search.size)
        assertEquals("Bat Fixture", search.single().title)

        val details = parser.getDetails(browse.single())
        assertEquals("Bat Fixture Detailed", details.title)
        assertEquals("Bat deterministic description.", details.description)
        assertEquals("Fixture Writer", details.authors.single())
        assertTrue(details.tags.any { it.title == "Action" })

        val chapters = requireNotNull(details.chapters)
        assertEquals(1, chapters.size)
        assertEquals("Chapter 1", chapters.single().title)
        assertEquals("/reader/77/1", chapters.single().url)
        assertEquals(1f, chapters.single().number)

        val pages = parser.getPages(chapters.single())
        assertEquals(2, pages.size)
        assertEquals("https://cdn.bat.test/001.jpg", pages[0].url)
        assertEquals("https://batcave.biz/uploads/002.jpg", pages[1].url)
        assertEquals(pages[0].url, parser.getPageUrl(pages[0]))
    }
}
