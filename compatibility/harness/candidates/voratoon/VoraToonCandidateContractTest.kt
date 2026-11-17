package compatibilityfarm

import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.id.VoraToon

/**
 * Synthetic Flight fixtures for the replacement parser, not live-site evidence.
 * Run against the candidate or the vendored implementation, not the legacy JSON parser.
 */
internal class VoraToonCandidateContractTest {
    @Test
    fun catalogueSearchDetailsAndReaderPreserveRelativeUrls() = runBlocking {
        val parser = VoraToon(DeterministicMangaLoaderContext { request ->
            val url = request.url
            assertEquals("voratoon.co", url.host)
            when (url.encodedPath) {
                "/browse" -> {
                    val slug = if (url.queryParameter("q") == "Fixture Search") "search-result" else "fixture"
                    FixtureResponse(flight("""{"series":[{"data":{"slug":"$slug","title":"Fixture VoraToon"}}],"seriesMeta":{}}"""))
                }
                "/series/fixture" -> FixtureResponse(flight(
                    """{"series":[{"data":{"title":"Fixture detail"}}],"chapters":[{"chapterIndex":1.5,"data":{"title":"Fractional"}}]}""",
                ))
                "/series/fixture/chapter/1.5" -> FixtureResponse(
                    """<html><img data-chapter-page="https://images.example.invalid/001.jpg"></html>""",
                )
                else -> error("Unexpected VoraToon request path: ${url.encodedPath}")
            }
        })
        val manga = parser.getList(0, SortOrder.POPULARITY, MangaListFilter()).single()
        assertEquals("/series/fixture", manga.url)
        assertEquals(
            "/series/search-result",
            parser.getList(0, SortOrder.POPULARITY, MangaListFilter(query = "Fixture Search")).single().url,
        )
        val detail = parser.getDetails(manga)
        assertEquals("Fixture detail", detail.title)
        assertEquals(manga.id, detail.id)
        val chapter = requireNotNull(detail.chapters).single()
        assertEquals("/series/fixture/chapter/1.5", chapter.url)
        assertEquals("https://images.example.invalid/001.jpg", parser.getPages(chapter).single().url)
    }

    private fun flight(page: String): String {
        val push = JSONArray().put(1).put("0:$page\n")
        return "<html><script>self.__next_f.push($push)</script></html>"
    }
}
