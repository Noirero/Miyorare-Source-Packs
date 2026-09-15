package compatibilityfarm

import kotlinx.coroutines.runBlocking
import okhttp3.Request
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.id.Komiku

internal class KomikuParserHarnessTest {

    private fun resource(path: String): String =
        checkNotNull(javaClass.getResource(path)) { "Missing fixture resource: $path" }.readText()

    private fun context(): DeterministicMangaLoaderContext =
        DeterministicMangaLoaderContext { request: Request ->
            val url = request.url
            val resource = when {
                url.host == "api.komiku.org" && url.encodedPath == "/manga/page/1/" ->
                    "/compatibility-farm/komiku/list.html"
                url.host == "api.komiku.org" && url.encodedPath == "/" && url.queryParameter("s") == "Sample" ->
                    "/compatibility-farm/komiku/list.html"
                url.host == "komiku.org" && url.encodedPath == "/manga/sample/" ->
                    "/compatibility-farm/komiku/details.html"
                url.host == "komiku.org" && url.encodedPath == "/ch/sample-1/" ->
                    "/compatibility-farm/komiku/pages.html"
                else -> error("Unexpected parser request: $url")
            }
            FixtureResponse(body = resource(resource))
        }

    @Test
    fun browseSearchDetailsChaptersAndPagesUseRealParserCode() = runBlocking {
        val parser = Komiku(context())

        val browse = parser.getList(
            offset = 0,
            order = SortOrder.UPDATED,
            filter = MangaListFilter(),
        )
        assertEquals(1, browse.size)
        assertEquals("Sample Manga", browse.single().title)
        assertEquals("/manga/sample/", browse.single().url)
        assertTrue(browse.single().coverUrl?.contains("cover.jpg") == true)

        val search = parser.getList(
            offset = 0,
            order = SortOrder.UPDATED,
            filter = MangaListFilter(query = "Sample"),
        )
        assertEquals(1, search.size)
        assertEquals("Sample Manga", search.single().title)

        val details = parser.getDetails(browse.single())
        assertEquals("Fixture description from Komiku details.", details.description)
        assertEquals("Fixture Author", details.authors.single())
        assertNotNull(details.state)

        val chapters = requireNotNull(details.chapters)
        assertEquals(1, chapters.size)
        assertEquals("Chapter 1", chapters.single().title)
        assertEquals("/ch/sample-1/", chapters.single().url)

        val pages = parser.getPages(chapters.single())
        assertEquals(2, pages.size)
        assertEquals("https://cdn.example.test/page-1.jpg", pages[0].url)
        assertEquals("https://cdn.example.test/page-2.jpg", pages[1].url)
        assertEquals(pages[0].url, parser.getPageUrl(pages[0]))
    }
}
