package compatibilityfarm

import eu.kanade.tachiyomi.multisrc.natsuid.NatsuId
import eu.kanade.tachiyomi.multisrc.natsuid.SortFilter
import eu.kanade.tachiyomi.network.DeterministicNetwork
import eu.kanade.tachiyomi.network.DeterministicNetwork.FixtureResponse
import eu.kanade.tachiyomi.source.model.FilterList
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okio.Buffer
import okhttp3.Request
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import uy.kohesive.injekt.Injekt
import uy.kohesive.injekt.api.addSingleton
import java.util.Collections

class KeiyoushiKiryuuParserHarnessTest {

    companion object {
        @JvmStatic
        @BeforeClass
        fun installHostServices() {
            // Keiyoushi's real jsonInstance is resolved from Injekt. The Android host
            // registers this service; the deterministic JVM harness must provide the
            // same host contract before NatsuId touches keiyoushi.utils.JsonKt.
            Injekt.addSingleton(Json { ignoreUnknownKeys = true })
        }
    }

    @Test
    fun executesPinnedKiryuuNatsuParserEndToEndWithoutLiveNetwork() = runBlocking {
        val observed = Collections.synchronizedList(mutableListOf<Request>())
        DeterministicNetwork.install { request ->
            observed += request
            val url = request.url
            when {
                request.method == "GET" &&
                    url.encodedPath == "/wp-admin/admin-ajax.php" &&
                    url.queryParameter("action") == "get_nonce" -> FixtureResponse(
                    "<input name=\"search_nonce\" value=\"fixture-nonce\">",
                )

                request.method == "POST" &&
                    url.encodedPath == "/wp-admin/admin-ajax.php" &&
                    url.queryParameter("action") == "advanced_search" -> FixtureResponse(
                    """
                    <div>
                      <a href="https://v7.kiryuu.to/manga/alpha/"><img src="/cover.jpg"></a>
                    </div>
                    """.trimIndent(),
                )

                request.method == "GET" &&
                    url.encodedPath == "/wp-json/wp/v2/manga" &&
                    url.queryParameterValues("slug[]").contains("alpha") -> FixtureResponse(
                    "[${mangaJson()}]",
                    "application/json; charset=utf-8",
                )

                request.method == "GET" &&
                    url.encodedPath == "/wp-json/wp/v2/manga/123" -> FixtureResponse(
                    mangaJson(),
                    "application/json; charset=utf-8",
                )

                request.method == "GET" &&
                    url.encodedPath == "/wp-admin/admin-ajax.php" &&
                    url.queryParameter("action") == "chapter_list" -> FixtureResponse(
                    """
                    <div>
                      <a href="https://v7.kiryuu.to/manga/alpha/chapter-1/">
                        <span>Chapter 1</span>
                        <time datetime="2026-01-01T00:00:00Z"></time>
                      </a>
                    </div>
                    """.trimIndent(),
                )

                request.method == "GET" &&
                    url.encodedPath == "/manga/alpha/chapter-1/" -> FixtureResponse(
                    """
                    <main>
                      <div class="relative">
                        <section><img src="/images/001.jpg"></section>
                        <section><img src="/images/002.jpg"></section>
                      </div>
                    </main>
                    """.trimIndent(),
                )

                else -> error("Unexpected parser request: ${request.method} $url")
            }
        }

        try {
            val source = newSource()

            val popular = source.getPopularManga(1)
            assertFalse(popular.hasNextPage)
            assertEquals(1, popular.mangas.size)
            val manga = popular.mangas.single()
            assertEquals("Alpha", manga.title)
            assertEquals("Fixture Author", manga.author)
            assertEquals("Fixture Artist", manga.artist)
            assertEquals("Action, Manga", manga.genre)
            assertEquals("https://v7.kiryuu.to/cover.jpg", manga.thumbnail_url)

            val searched = source.getSearchMangaList(1, "Alpha", FilterList(SortFilter(0)))
            assertEquals(1, searched.mangas.size)
            assertEquals("Alpha", searched.mangas.single().title)

            val urlResolved = source.getSearchManga(
                1,
                "https://v7.kiryuu.to/manga/alpha/",
                FilterList(),
            )
            assertEquals(1, urlResolved.mangas.size)
            assertEquals("Alpha", urlResolved.mangas.single().title)

            val update = source.getMangaUpdate(
                manga = manga,
                chapters = emptyList(),
                fetchDetails = true,
                fetchChapters = true,
            )
            assertEquals("Alpha", update.manga.title)
            assertEquals(1, update.chapters.size)
            val chapter = update.chapters.single()
            assertEquals("Chapter 1", chapter.name)
            assertEquals("/manga/alpha/chapter-1/", chapter.url)
            assertTrue(chapter.date_upload > 0L)

            val pages = source.getPageList(chapter)
            assertEquals(2, pages.size)
            assertEquals("https://v7.kiryuu.to/images/001.jpg", pages[0].imageUrl)
            assertEquals("https://v7.kiryuu.to/images/002.jpg", pages[1].imageUrl)

            val chapterRequest = observed.first {
                it.method == "GET" &&
                    it.url.encodedPath == "/wp-admin/admin-ajax.php" &&
                    it.url.queryParameter("action") == "chapter_list"
            }
            assertEquals("1", chapterRequest.url.queryParameter("page"))

            val searchPost = observed.last {
                it.method == "POST" &&
                    it.url.encodedPath == "/wp-admin/admin-ajax.php" &&
                    it.url.queryParameter("action") == "advanced_search"
            }
            val body = Buffer().also { searchPost.body!!.writeTo(it) }.readUtf8()
            assertTrue(body.contains("fixture-nonce"))
            assertTrue(body.contains("Alpha"))
            assertTrue(observed.none { it.url.host != "v7.kiryuu.to" })
        } finally {
            DeterministicNetwork.clear()
        }
    }

    private fun newSource(): NatsuId {
        val generated = Class.forName("keiyoushi.source.Generated")
        return generated.getDeclaredConstructor().apply { isAccessible = true }.newInstance() as NatsuId
    }

    private fun mangaJson() = """
        {
          "id": 123,
          "slug": "alpha",
          "title": {"rendered": "Alpha"},
          "content": {"rendered": "<p>Fixture synopsis.</p>"},
          "_embedded": {
            "wp:featuredmedia": [
              {"source_url": "https://v7.kiryuu.to/cover.jpg"}
            ],
            "wp:term": [
              [{"name": "Fixture Author", "slug": "fixture-author", "taxonomy": "series-author"}],
              [{"name": "Fixture Artist", "slug": "fixture-artist", "taxonomy": "artist"}],
              [{"name": "Action", "slug": "action", "taxonomy": "genre"}],
              [{"name": "Manga", "slug": "manga", "taxonomy": "type"}],
              [{"name": "Ongoing", "slug": "ongoing", "taxonomy": "status"}]
            ]
          }
        }
    """.trimIndent()
}
