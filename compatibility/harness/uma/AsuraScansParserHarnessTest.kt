package compatibilityfarm

import kotlinx.coroutines.runBlocking
import okhttp3.Request
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.en.AsuraScansParser

internal class AsuraScansParserHarnessTest {

    private fun context(): DeterministicMangaLoaderContext =
        DeterministicMangaLoaderContext { request: Request ->
            assertEquals("asurascans.com", request.url.host)
            val body = when {
                request.url.encodedPath == "/browse" -> {
                    assertEquals("GET", request.method)
                    assertEquals("0", request.url.queryParameter("page"))
                    listHtml()
                }

                request.url.encodedPath == "/comics/asura-fixture" -> """
                    <html><body>
                      <article><h1>Asura Fixture Detailed</h1></article>
                      <div id="alt-titles">Fixture Alternate • Fixture Other</div>
                      <div id="description-text"><p>Asura deterministic description.</p></div>
                      <div class="space-y-2"><div class="flex"><button class="text-white">Action</button></div></div>
                      <div class="grid"><div><h3>Author</h3><h3>Fixture Author</h3></div></div>
                      <a class="group" href="/comics/asura-fixture/chapter/1">
                        <span class="font-medium">Chapter 1</span>
                        <span class="text-sm text-white/50">First Step</span>
                        <span class="text-sm text-white/40">Jan 1, 2026</span>
                      </a>
                    </body></html>
                """.trimIndent()

                request.url.encodedPath == "/comics/asura-fixture/chapter/1" -> """
                    <html><body>
                      <astro-island component-url="/components/ChapterReader.js"
                        props='{"url":[0,"https://cdn.asura.test/001.jpg"],"other":{"url":[0,"https://cdn.asura.test/002.jpg"]}}'>
                      </astro-island>
                    </body></html>
                """.trimIndent()

                else -> error("Unexpected Asura parser request: ${request.method} ${request.url}")
            }
            FixtureResponse(body = body)
        }

    private fun listHtml(): String = """
        <html><body>
          <div id="series-grid">
            <div class="series-card">
              <a href="/comics/asura-fixture"><img src="https://cdn.asura.test/cover.jpg"></a>
              <h3>Asura Fixture</h3>
              <div class="absolute top-2 right-2"><span>4.5</span></div>
              <div class="p-3"><span>Type</span><span>Ongoing</span></div>
            </div>
          </div>
        </body></html>
    """.trimIndent()

    @Test
    fun browseSearchDetailsChaptersAndAstroPagesUseRealParserCode() = runBlocking {
        val parser = AsuraScansParser(context())

        val browse = parser.getList(
            offset = 0,
            order = SortOrder.UPDATED,
            filter = MangaListFilter(),
        )
        assertEquals(1, browse.size)
        assertEquals("Asura Fixture", browse.single().title)
        assertEquals("/comics/asura-fixture", browse.single().url)

        val search = parser.getList(
            offset = 0,
            order = SortOrder.RATING,
            filter = MangaListFilter(query = "Fixture"),
        )
        assertEquals(1, search.size)
        assertEquals("Asura Fixture", search.single().title)

        val details = parser.getDetails(browse.single())
        assertEquals("Asura Fixture Detailed", details.title)
        assertTrue(details.altTitles.contains("Fixture Alternate"))
        assertTrue(details.description.orEmpty().contains("Asura deterministic description."))
        assertEquals("Fixture Author", details.authors.single())
        assertTrue(details.tags.any { it.title == "Action" })

        val chapters = requireNotNull(details.chapters)
        assertEquals(1, chapters.size)
        assertEquals("Chapter 1 - First Step", chapters.single().title)
        assertEquals(1f, chapters.single().number)
        assertEquals("/comics/asura-fixture/chapter/1", chapters.single().url)

        val pages = parser.getPages(chapters.single())
        assertEquals(2, pages.size)
        assertEquals("https://cdn.asura.test/001.jpg", pages[0].url)
        assertEquals("https://cdn.asura.test/002.jpg", pages[1].url)
    }
}
