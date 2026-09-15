package compatibilityfarm

import kotlinx.coroutines.runBlocking
import okhttp3.Request
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.id.DoujinDesuParser

internal class DoujinDesuParserHarnessTest {

    private fun resource(path: String): String =
        checkNotNull(javaClass.getResource(path)) { "Missing fixture resource: $path" }.readText()

    @Test
    fun browseDetailsChaptersAndAjaxPagesUseRealParserCode() = runBlocking {
        val observed = mutableListOf<Request>()
        val context = DeterministicMangaLoaderContext { request ->
            observed += request
            val url = request.url
            val fixture = when {
                request.method == "GET" && url.encodedPath == "/manga" ->
                    "/compatibility-farm/doujindesu/list.html"
                request.method == "GET" && url.encodedPath == "/manga/sample/" ->
                    "/compatibility-farm/doujindesu/details.html"
                request.method == "GET" && url.encodedPath == "/chapter/sample-1/" ->
                    "/compatibility-farm/doujindesu/reader.html"
                request.method == "POST" && url.encodedPath == "/themes/ajax/ch.php" ->
                    "/compatibility-farm/doujindesu/pages.html"
                else -> error("Unexpected parser request: ${request.method} $url")
            }
            FixtureResponse(body = resource(fixture))
        }
        val parser = DoujinDesuParser(context)

        val browse = parser.getList(
            offset = 0,
            order = SortOrder.UPDATED,
            filter = MangaListFilter(),
        )
        assertEquals(1, browse.size)
        assertEquals("Fixture Doujin", browse.single().title)
        assertEquals("/manga/sample/", browse.single().url)

        val details = parser.getDetails(browse.single())
        assertEquals("Fixture Doujin description.", details.description)
        assertEquals("Fixture Author", details.authors.single())

        val chapters = requireNotNull(details.chapters)
        assertEquals(1, chapters.size)
        assertEquals("Chapter 1", chapters.single().title)
        assertEquals("/chapter/sample-1/", chapters.single().url)

        val pages = parser.getPages(chapters.single())
        assertEquals(2, pages.size)
        assertEquals("/images/page-1.jpg", pages[0].url)
        assertEquals("/images/page-2.jpg", pages[1].url)
        assertEquals("https://doujindesu.tv/images/page-1.jpg", parser.getPageUrl(pages[0]))
        assertTrue(observed.any { it.method == "POST" && it.url.encodedPath == "/themes/ajax/ch.php" })
    }
}
