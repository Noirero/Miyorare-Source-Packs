package compatibilityfarm

import eu.kanade.tachiyomi.extension.id.bacami.Bacami
import eu.kanade.tachiyomi.network.DeterministicNetwork
import eu.kanade.tachiyomi.network.DeterministicNetwork.FixtureResponse
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import uy.kohesive.injekt.Injekt
import uy.kohesive.injekt.api.addSingleton

class KeiyoushiBacamiParserHarnessTest {
    companion object {
        @JvmStatic
        @BeforeClass
        fun installHostServices() {
            Injekt.addSingleton(Json { ignoreUnknownKeys = true })
        }
    }

    @Test
    fun executesPinnedBacamiParserEndToEndWithoutLiveNetwork() = runBlocking {
        DeterministicNetwork.install { request ->
            val url = request.url
            when {
                request.method == "GET" && url.encodedPath == "/custom-search/orderby/score" -> FixtureResponse(
                    """
                    <article class="genre-card">
                      <div class="genre-cover"><a href="https://v1.bacami.site/komik/alpha/"><img src="https://v1.bacami.site/cover.jpg"></a></div>
                      <div class="genre-info"><a>Alpha Bacami</a></div>
                    </article>
                    """.trimIndent(),
                )
                request.method == "GET" && url.encodedPath == "/komik/alpha/" -> FixtureResponse(
                    """
                    <div id="komik">
                      <section class="manga-content">
                        <header><h1>Alpha Bacami Detailed</h1></header>
                        <figure><div class="image-wrap"><img src="https://v1.bacami.site/cover-detail.jpg"></div></figure>
                        <p class="manga-description">Fixture Bacami synopsis.</p>
                        <div class="info-item">Author <span class="info-value">Fixture Author</span></div>
                        <nav><span><a>Action</a></span></nav>
                      </section>
                    </div>
                    <span class="hot-tag">Hot</span>
                    <ol class="chapter-list">
                      <li>
                        <a class="ch-link" href="https://v1.bacami.site/komik/alpha/chapter-1/">Alpha – Chapter 1</a>
                        <span class="ch-date">1 January, 2026</span>
                      </li>
                    </ol>
                    """.trimIndent(),
                )
                request.method == "GET" && url.encodedPath == "/komik/alpha/chapter-1/" -> FixtureResponse(
                    """
                    <script>
                      window.reader = { imageUrls: ["https://v1.bacami.site/pages/001.jpg", "https://v1.bacami.site/pages/002.jpg"], next: true };
                    </script>
                    """.trimIndent(),
                )
                else -> error("Unexpected Bacami parser request: ${request.method} $url")
            }
        }

        try {
            val source = newSource()
            val popular = source.getPopularManga(1)
            assertFalse(popular.hasNextPage)
            assertEquals(1, popular.mangas.size)
            val manga = popular.mangas.single()
            assertEquals("Alpha Bacami", manga.title)
            assertEquals("/komik/alpha/", manga.url)

            val update = source.getMangaUpdate(
                manga = manga,
                chapters = emptyList(),
                fetchDetails = true,
                fetchChapters = true,
            )
            assertEquals("Alpha Bacami Detailed", update.manga.title)
            assertEquals("Fixture Author", update.manga.author)
            assertEquals("Action", update.manga.genre)
            assertEquals(1, update.chapters.size)
            val chapter = update.chapters.single()
            assertEquals("Chapter 1", chapter.name)
            assertTrue(chapter.date_upload > 0L)

            val pages = source.getPageList(chapter)
            assertEquals(2, pages.size)
            assertEquals("https://v1.bacami.site/pages/001.jpg", pages[0].imageUrl)
            assertEquals("https://v1.bacami.site/pages/002.jpg", pages[1].imageUrl)
        } finally {
            DeterministicNetwork.clear()
        }
    }

    private fun newSource(): Bacami {
        val generated = Class.forName("keiyoushi.source.Generated")
        return generated.getDeclaredConstructor().apply { isAccessible = true }.newInstance() as Bacami
    }
}
