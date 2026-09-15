package compatibilityfarm

import kotlinx.coroutines.runBlocking
import okhttp3.Cookie
import okhttp3.Request
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.en.WeebCentral

internal class WeebCentralAuthParserHarnessTest {

    private fun resource(path: String): String =
        checkNotNull(javaClass.getResource(path)) { "Missing fixture resource: $path" }.readText()

    @Test
    fun cookieAuthUsernameBrowseSearchDetailsChaptersAndPagesUseRealParserCode() = runBlocking {
        val anonymous = DeterministicMangaLoaderContext(
            responder = { error("Anonymous auth check must not perform network I/O") },
        )
        assertFalse(WeebCentral(anonymous).isAuthorized())

        val accessToken = Cookie.Builder()
            .name("access_token")
            .value("fixture-token")
            .domain("weebcentral.com")
            .path("/")
            .build()
        val observed = mutableListOf<Request>()
        val context = DeterministicMangaLoaderContext(
            responder = { request ->
                observed += request
                assertTrue(request.header("Cookie")?.contains("access_token=fixture-token") == true)
                val fixture = when (request.url.encodedPath) {
                    "/users/me/profiles" -> "/compatibility-farm/weebcentral/profile.html"
                    "/search/data" -> "/compatibility-farm/weebcentral/list.html"
                    "/series/series-1" -> "/compatibility-farm/weebcentral/details.html"
                    "/chapters/chapter-1/images" -> "/compatibility-farm/weebcentral/pages.html"
                    else -> error("Unexpected Weeb Central request: ${request.method} ${request.url}")
                }
                FixtureResponse(body = resource(fixture))
            },
            seededCookies = listOf(accessToken),
        )
        val parser = WeebCentral(context)

        assertTrue(parser.isAuthorized())
        assertEquals("Fixture Reader", parser.getUsername())

        val browse = parser.getList(
            offset = 0,
            order = SortOrder.UPDATED,
            filter = MangaListFilter(),
        )
        assertEquals(1, browse.size)
        assertEquals("Fixture Weeb", browse.single().title)
        assertEquals("series-1", browse.single().url)
        assertEquals("Fixture Author", browse.single().authors.single())

        val search = parser.getList(
            offset = 0,
            order = SortOrder.RELEVANCE,
            filter = MangaListFilter(query = "Fixture!!!"),
        )
        assertEquals(1, search.size)
        assertTrue(observed.any { it.url.encodedPath == "/search/data" && it.url.queryParameter("text") == "Fixture" })

        val details = parser.getDetails(browse.single())
        assertEquals("Fixture Weeb Detailed", details.title)
        assertEquals("Fixture Author", details.authors.single())
        assertTrue(details.description.orEmpty().contains("Fixture authenticated description."))

        val chapters = requireNotNull(details.chapters)
        assertEquals(1, chapters.size)
        assertEquals("Chapter 1", chapters.single().title)
        assertEquals("chapter-1", chapters.single().url)
        assertEquals(1f, chapters.single().number)

        val pages = parser.getPages(chapters.single())
        assertEquals(2, pages.size)
        assertEquals("https://images.weeb.test/chapter-1/001.jpg", pages[0].url)
        assertEquals("https://images.weeb.test/chapter-1/002.jpg", pages[1].url)

        assertTrue(observed.isNotEmpty())
        assertTrue(observed.all { it.url.host == "weebcentral.com" })
        assertTrue(observed.all { it.header("Cookie")?.contains("access_token=fixture-token") == true })
    }
}
