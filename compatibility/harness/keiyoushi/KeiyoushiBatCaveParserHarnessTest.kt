package compatibilityfarm

import eu.kanade.tachiyomi.extension.en.batcave.BatCave
import eu.kanade.tachiyomi.network.DeterministicNetwork
import eu.kanade.tachiyomi.network.DeterministicNetwork.FixtureResponse
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.Request
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import uy.kohesive.injekt.Injekt
import uy.kohesive.injekt.api.addSingleton
import java.util.Collections

class KeiyoushiBatCaveParserHarnessTest {
    companion object {
        @JvmStatic
        @BeforeClass
        fun installHostServices() {
            Injekt.addSingleton(Json { ignoreUnknownKeys = true })
        }
    }

    @Test
    fun executesPinnedBatCaveParserBrowseDetailsChaptersAndReaderApi() = runBlocking {
        val observed = Collections.synchronizedList(mutableListOf<Request>())
        DeterministicNetwork.install { request ->
            observed += request
            val url = request.url
            when {
                request.method == "POST" && url.encodedPath == "/comix/" -> FixtureResponse(
                    """
                    <div id="dle-content">
                      <div class="readed">
                        <div class="readed__title"><a href="https://batcave.biz/comic/alpha">Alpha BatCave</a></div>
                        <div class="readed__img"><img data-src="https://batcave.biz/covers/alpha.jpg"></div>
                      </div>
                    </div>
                    """.trimIndent(),
                )
                request.method == "GET" && url.encodedPath == "/comic/alpha" -> FixtureResponse(
                    """
                    <header class="page__header"><h1>Alpha BatCave Detailed</h1></header>
                    <div class="page__poster"><img src="https://batcave.biz/covers/alpha-detail.jpg"></div>
                    <div class="page__text">Fixture BatCave synopsis.</div>
                    <div class="page__tags"><a>Action</a></div>
                    <ul class="page__list">
                      <li><div>Release type</div>Ongoing</li>
                    </ul>
                    <script>
                      window.__DATA__ = {"news_id":42,"chapters":[{"id":7,"posi":1.0,"title":"Chapter 1","date":"1.1.2026"}],"xhash":"x"};
                    </script>
                    """.trimIndent(),
                )
                request.method == "POST" &&
                    url.encodedPath == "/engine/ajax/controller.php" &&
                    url.queryParameter("mod") == "api" &&
                    url.queryParameter("action") == "reader/getChapterData" -> FixtureResponse(
                    """{"data":{"images":["/pages/001.jpg","https://batcave.biz/pages/002.jpg"]}}""",
                    "application/json; charset=utf-8",
                )
                else -> error("Unexpected BatCave parser request: ${request.method} $url")
            }
        }

        try {
            val source = newSource()
            val popular = source.getPopularManga(1)
            assertFalse(popular.hasNextPage)
            assertEquals(1, popular.mangas.size)
            val manga = popular.mangas.single()
            assertEquals("Alpha BatCave", manga.title)
            assertEquals("/comic/alpha", manga.url)

            val update = source.getMangaUpdate(
                manga = manga,
                chapters = emptyList(),
                fetchDetails = true,
                fetchChapters = true,
            )
            assertEquals("Alpha BatCave Detailed", update.manga.title)
            assertTrue(update.manga.genre.orEmpty().contains("Action"))
            assertEquals(1, update.chapters.size)
            val chapter = update.chapters.single()
            assertEquals("Chapter 1", chapter.name)
            assertEquals("/reader/42/7x", chapter.url)

            val pages = source.getPageList(chapter)
            assertEquals(2, pages.size)
            assertEquals("https://batcave.biz/pages/001.jpg", pages[0].imageUrl)
            assertEquals("https://batcave.biz/pages/002.jpg", pages[1].imageUrl)

            val popularRequest = observed.first { it.method == "POST" && it.url.encodedPath == "/comix/" }
            assertEquals("document", popularRequest.header("Sec-Fetch-Dest"))
            assertEquals("navigate", popularRequest.header("Sec-Fetch-Mode"))
            assertTrue(observed.none { it.url.host != "batcave.biz" })
        } finally {
            DeterministicNetwork.clear()
        }
    }

    private fun newSource(): BatCave {
        val generated = Class.forName("keiyoushi.source.Generated")
        return generated.getDeclaredConstructor().apply { isAccessible = true }.newInstance() as BatCave
    }
}
