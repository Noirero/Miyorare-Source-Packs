package compatibilityfarm

import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import okhttp3.Call
import okhttp3.Connection
import okhttp3.Interceptor
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder
import tsuki.site.en.LikeManga

internal class LikeMangaParserHarnessBehaviorTest {
    @Test
    fun sharedParserAndSourceUserAgentInterceptorExecuteRealCode() = runBlocking {
        val context = DeterministicMangaLoaderContext { request ->
            val url = request.url
            when {
                url.host == "likemanga.ink" && url.encodedPath == "/" && url.queryParameter("act") == "search" -> FixtureResponse(
                    """
                    <div class="card-body">
                      <div class="video">
                        <a href="/manga/fixture-like-123/"><img src="https://likemanga.ink/covers/alpha.jpg"></a>
                        <p class="title-manga">Fixture LikeManga</p>
                      </div>
                    </div>
                    """.trimIndent(),
                )
                url.host == "likemanga.ink" && url.encodedPath == "/manga/fixture-like-123/" -> FixtureResponse(
                    """
                    <ul class="list-info"><li class="othername"><h2>Fixture Alt</h2></li></ul>
                    <li class="author"><p>Fixture Author</p></li>
                    <li class="kind"><a href="/genres/action/">Action</a></li>
                    <div id="summary_shortened"><p>Fixture LikeManga synopsis.</p></div>
                    <ul>
                      <li class="wp-manga-chapter">
                        <a href="/manga/fixture-like-123/chapter-1/">Chapter 1</a>
                        <span class="chapter-release-date">January 1, 2026</span>
                      </li>
                    </ul>
                    """.trimIndent(),
                )
                url.host == "likemanga.ink" && url.encodedPath == "/manga/fixture-like-123/chapter-1/" -> FixtureResponse(
                    """
                    <div class="reading-detail"><img src="https://likemanga.ink/pages/001.jpg"></div>
                    <div class="reading-detail"><img src="https://likemanga.ink/pages/002.jpg"></div>
                    """.trimIndent(),
                )
                else -> error("Unexpected LikeManga parser request: ${request.method} $url")
            }
        }

        val parser = LikeManga(context)
        val browse = parser.getList(0, SortOrder.UPDATED, MangaListFilter())
        assertEquals(1, browse.size)
        assertEquals("Fixture LikeManga", browse.single().title)

        val details = parser.getDetails(browse.single())
        assertEquals("Fixture Author", details.authors.single())
        val chapter = requireNotNull(details.chapters).single()
        assertEquals("Chapter 1", chapter.title)

        val pages = parser.getPages(chapter)
        assertEquals(2, pages.size)
        assertTrue(pages[0].url.endsWith("/pages/001.jpg"))
        assertTrue(pages[1].url.endsWith("/pages/002.jpg"))

        val chain = CapturingChain(Request.Builder().url("https://likemanga.ink/").build())
        parser.intercept(chain)
        assertEquals("Usagi/1 (Android)", requireNotNull(chain.proceeded).header("User-Agent"))
    }
}

private class CapturingChain(
    private val original: Request,
) : Interceptor.Chain {
    var proceeded: Request? = null
        private set

    override fun request(): Request = original

    override fun proceed(request: Request): Response {
        proceeded = request
        return Response.Builder()
            .request(request)
            .protocol(Protocol.HTTP_1_1)
            .code(200)
            .message("OK")
            .body("".toResponseBody(null))
            .build()
    }

    override fun connection(): Connection? = null
    override fun call(): Call = error("Call is not used by LikeManga interceptor")
    override fun connectTimeoutMillis(): Int = 0
    override fun readTimeoutMillis(): Int = 0
    override fun writeTimeoutMillis(): Int = 0
    override fun withConnectTimeout(timeout: Int, unit: TimeUnit): Interceptor.Chain = this
    override fun withReadTimeout(timeout: Int, unit: TimeUnit): Interceptor.Chain = this
    override fun withWriteTimeout(timeout: Int, unit: TimeUnit): Interceptor.Chain = this
}
