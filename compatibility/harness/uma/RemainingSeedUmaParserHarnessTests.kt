package compatibilityfarm

import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.en.MangaPill
import tsuki.site.id.Bacami
import tsuki.site.id.TheManga

internal class BacamiParserHarnessTest {
    @Test
    fun browseDetailsChaptersAndScriptPagesUseRealParserCode() = runBlocking {
        val context = DeterministicMangaLoaderContext { request ->
            val url = request.url
            when {
                url.host == "v1.bacami.site" && url.encodedPath == "/custom-search/orderby/score/page/1/" -> FixtureResponse(
                    """
                    <article class="genre-card">
                      <div class="genre-cover"><a href="/komik/alpha/"><img src="/cover.jpg"></a></div>
                      <div class="genre-info"><a>Alpha Bacami</a></div>
                    </article>
                    """.trimIndent(),
                )
                url.host == "v1.bacami.site" && url.encodedPath == "/komik/alpha/" -> FixtureResponse(
                    """
                    <div id="komik">
                      <section class="manga-content">
                        <header><h1>Alpha Bacami Detailed</h1></header>
                        <figure><div class="image-wrap"><img src="/cover-detail.jpg"></div></figure>
                        <p class="manga-description">Fixture Bacami synopsis.</p>
                        <div class="info-item">Author <span class="info-value">Fixture Author</span></div>
                        <nav><span><a>Action</a></span></nav>
                      </section>
                    </div>
                    <span class="hot-tag">Hot</span>
                    <ol class="chapter-list">
                      <li><a class="ch-link" href="/komik/alpha/chapter-1/">Alpha – Chapter 1</a><span class="ch-date">01 January, 2026</span></li>
                    </ol>
                    """.trimIndent(),
                )
                url.host == "v1.bacami.site" && url.encodedPath == "/komik/alpha/chapter-1/" -> FixtureResponse(
                    """
                    <script>
                      window.reader = { imageUrls: ["https://v1.bacami.site/pages/001.jpg", "https://v1.bacami.site/pages/002.jpg"], other: true };
                    </script>
                    """.trimIndent(),
                )
                else -> error("Unexpected Bacami parser request: ${request.method} $url")
            }
        }

        val parser = Bacami(context)
        val browse = parser.getList(0, SortOrder.POPULARITY, MangaListFilter())
        assertEquals(1, browse.size)
        assertEquals("Alpha Bacami", browse.single().title)

        val details = parser.getDetails(browse.single())
        assertEquals("Alpha Bacami Detailed", details.title)
        assertEquals("Fixture Bacami synopsis.", details.description)
        val chapter = requireNotNull(details.chapters).single()
        assertEquals("Chapter 1", chapter.title)

        val pages = parser.getPages(chapter)
        assertEquals(2, pages.size)
        assertTrue(pages[0].url.endsWith("/pages/001.jpg"))
        assertTrue(pages[1].url.endsWith("/pages/002.jpg"))
    }
}

internal class MangaPillParserHarnessTest {
    @Test
    fun popularDetailsChaptersAndPagesUseRealParserCode() = runBlocking {
        val context = DeterministicMangaLoaderContext { request ->
            val url = request.url
            when {
                url.host == "mangapill.com" && url.encodedPath == "/" -> FixtureResponse(
                    """
                    <div>
                      <h4>Trending</h4>
                      <div class="grid">
                        <div>
                          <a href="/manga/alpha"><div class="line-clamp-2">Fixture MangaPill</div><img data-src="https://mangapill.com/covers/alpha.jpg"></a>
                        </div>
                      </div>
                    </div>
                    """.trimIndent(),
                )
                url.host == "mangapill.com" && url.encodedPath == "/manga/alpha" -> FixtureResponse(
                    """
                    <div class="container">
                      <div>
                        <div><img data-src="https://mangapill.com/covers/alpha-detail.jpg"></div>
                        <div><div></div><div><p>Fixture MangaPill synopsis.</p></div></div>
                      </div>
                    </div>
                    <div id="chapters"><a href="/chapters/alpha-chapter-1">Chapter 1</a></div>
                    """.trimIndent(),
                )
                url.host == "mangapill.com" && url.encodedPath == "/chapters/alpha-chapter-1" -> FixtureResponse(
                    """
                    <picture><img data-src="https://mangapill.com/pages/001.jpg"></picture>
                    <picture><img data-src="https://mangapill.com/pages/002.jpg"></picture>
                    """.trimIndent(),
                )
                else -> error("Unexpected MangaPill parser request: ${request.method} $url")
            }
        }

        val parser = MangaPill(context)
        val browse = parser.getList(0, SortOrder.POPULARITY, MangaListFilter())
        assertEquals(1, browse.size)
        assertEquals("Fixture MangaPill", browse.single().title)

        val details = parser.getDetails(browse.single())
        val chapter = requireNotNull(details.chapters).single()
        assertEquals("Chapter 1", chapter.title)

        val pages = parser.getPages(chapter)
        assertEquals(2, pages.size)
        assertTrue(pages[0].url.endsWith("/pages/001.jpg"))
    }
}

internal class TheMangaParserHarnessTest {
    @Test
    fun listTwoStepDetailsChaptersAndPagesUseRealParserCode() = runBlocking {
        val context = DeterministicMangaLoaderContext { request ->
            val url = request.url
            when {
                url.host == "themanga.site" && url.encodedPath == "/" && url.queryParameter("sort") == "popular" -> FixtureResponse(
                    """
                    <a class="card" href="/manga/alpha">
                      <div class="card-title">Fixture TheManga</div>
                      <div class="card-cover"><img src="https://themanga.site/covers/alpha.jpg"></div>
                    </a>
                    """.trimIndent(),
                )
                url.host == "themanga.site" && url.encodedPath == "/manga/alpha" && url.queryParameter("all") == "1" -> FixtureResponse(
                    """
                    <div class="chapter-row" data-href="/manga/alpha/chapter/1.00">
                      <div class="chapter-title">Chapter 1</div>
                      <time data-local-time="2026-01-01T00:00:00+00:00"></time>
                    </div>
                    """.trimIndent(),
                )
                url.host == "themanga.site" && url.encodedPath == "/manga/alpha" -> FixtureResponse(
                    """
                    <div class="hero-title">Fixture TheManga Detailed</div>
                    <div class="hero-cover"><img src="https://themanga.site/covers/alpha-detail.jpg"></div>
                    <div class="synopsis-text">Fixture TheManga synopsis.</div>
                    <span class="hero-status-badge">Ongoing</span>
                    <span class="meta-item-label">Author</span><span class="meta-item-value">Fixture Author</span>
                    <div class="meta-pill-row"><span class="meta-pill">Action</span></div>
                    """.trimIndent(),
                )
                url.host == "themanga.site" && url.encodedPath == "/manga/alpha/chapter/1.00" -> FixtureResponse(
                    """
                    <img class="page-img" src="https://themanga.site/pages/001.jpg">
                    <img class="page-img" src="https://themanga.site/pages/002.jpg">
                    """.trimIndent(),
                )
                else -> error("Unexpected TheManga parser request: ${request.method} $url")
            }
        }

        val parser = TheManga(context)
        val browse = parser.getList(0, SortOrder.POPULARITY, MangaListFilter())
        assertEquals(1, browse.size)
        assertEquals("Fixture TheManga", browse.single().title)

        val details = parser.getDetails(browse.single())
        assertEquals("Fixture TheManga Detailed", details.title)
        val chapter = requireNotNull(details.chapters).single()
        assertEquals("Chapter 1", chapter.title)

        val pages = parser.getPages(chapter)
        assertEquals(2, pages.size)
        assertTrue(pages[0].url.endsWith("/pages/001.jpg"))
    }
}
