package compatibilityfarm

import kotlinx.coroutines.runBlocking
import okhttp3.Request
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.id.Shinigami

internal class ShinigamiParserHarnessTest {

    private fun resource(path: String): String =
        checkNotNull(javaClass.getResource(path)) { "Missing fixture resource: $path" }.readText()

    @Test
    fun browseSearchDetailsChaptersPagesAndApiHeadersUseRealParserCode() = runBlocking {
        val observed = mutableListOf<Request>()
        val context = DeterministicMangaLoaderContext { request ->
            observed += request
            val url = request.url
            assertEquals("application/json", request.header("Accept"))
            assertEquals("https://g.shinigami.asia", request.header("Origin"))
            assertEquals("https://g.shinigami.asia/", request.header("referer"))

            val fixture = when (url.encodedPath) {
                "/v1/manga/list" -> "/compatibility-farm/shinigami/list.json"
                "/v1/manga/detail/manga-1" -> "/compatibility-farm/shinigami/details.json"
                "/v1/chapter/manga-1/list" -> "/compatibility-farm/shinigami/chapters.json"
                "/v1/chapter/detail/chapter-1" -> "/compatibility-farm/shinigami/pages.json"
                else -> error("Unexpected parser request: $url")
            }
            FixtureResponse(
                body = resource(fixture),
                contentType = "application/json; charset=utf-8",
            )
        }
        val parser = Shinigami(context)

        val browse = parser.getList(
            offset = 0,
            order = SortOrder.NEWEST,
            filter = MangaListFilter(),
        )
        assertEquals(1, browse.size)
        assertEquals("Fixture Shinigami", browse.single().title)
        assertEquals("/manga/detail/manga-1", browse.single().url)
        assertEquals("Fixture Author", browse.single().authors.single())

        val search = parser.getList(
            offset = 0,
            order = SortOrder.NEWEST,
            filter = MangaListFilter(query = "Fixture"),
        )
        assertEquals(1, search.size)
        assertTrue(observed.any { it.url.queryParameter("q") == "Fixture" })

        val details = parser.getDetails(browse.single())
        assertEquals("Updated fixture description", details.description)
        assertEquals("Fixture Author", details.authors.single())

        val chapters = requireNotNull(details.chapters)
        assertEquals(1, chapters.size)
        assertEquals("Chapter 1", chapters.single().title)
        assertEquals("/chapter/detail/chapter-1", chapters.single().url)

        val pages = parser.getPages(chapters.single())
        assertEquals(2, pages.size)
        assertEquals("https://images.example.test/manga-1/chapter-1/001.jpg", pages[0].url)
        assertEquals("https://images.example.test/manga-1/chapter-1/002.jpg", pages[1].url)
        assertEquals(pages[0].url, parser.getPageUrl(pages[0]))
    }
}
