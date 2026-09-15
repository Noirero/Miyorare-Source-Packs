package compatibilityfarm

import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import tsuki.MangaLoaderContext
import tsuki.MangaParser
import tsuki.bitmap.Bitmap
import tsuki.config.ConfigKey
import tsuki.config.MangaSourceConfig
import tsuki.model.MangaSource

internal data class FixtureResponse(
    val body: String,
    val contentType: String = "text/html; charset=utf-8",
    val code: Int = 200,
)

/**
 * JVM-only deterministic context used by Compatibility Farm parser execution tests.
 * Every network request must be satisfied by the supplied fixture responder; unexpected
 * requests fail closed instead of reaching the public network.
 *
 * Seeded cookies model host-provided authenticated state without contacting a real site.
 */
internal class DeterministicMangaLoaderContext(
    private val responder: (Request) -> FixtureResponse,
    seededCookies: List<Cookie> = emptyList(),
) : MangaLoaderContext() {

    private val storedCookies = seededCookies.toMutableList()

    override val cookieJar: CookieJar = object : CookieJar {
        override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
            cookies.forEach { incoming ->
                storedCookies.removeAll {
                    it.name == incoming.name && it.domain == incoming.domain && it.path == incoming.path
                }
                storedCookies += incoming
            }
        }

        override fun loadForRequest(url: HttpUrl): List<Cookie> = storedCookies.filter { it.matches(url) }
    }

    override val httpClient: OkHttpClient = OkHttpClient.Builder()
        .addInterceptor { chain ->
            val original = chain.request()
            val cookies = cookieJar.loadForRequest(original.url)
            val request = if (cookies.isEmpty()) {
                original
            } else {
                original.newBuilder()
                    .header("Cookie", cookies.joinToString("; ") { "${it.name}=${it.value}" })
                    .build()
            }
            val fixture = responder(request)
            Response.Builder()
                .request(request)
                .protocol(Protocol.HTTP_1_1)
                .code(fixture.code)
                .message(if (fixture.code in 200..299) "OK" else "Fixture error")
                .body(fixture.body.toResponseBody(fixture.contentType.toMediaType()))
                .build()
        }
        .build()

    override fun newParserInstance(source: MangaSource): MangaParser =
        error("Parser factory is not used by deterministic parser harness tests")

    override fun getParserSources(): List<MangaSource> = emptyList()

    @Deprecated("Provide a base url")
    override suspend fun evaluateJs(script: String): String? = null

    override suspend fun evaluateJs(baseUrl: String, script: String): String? = null

    override fun getConfig(source: MangaSource): MangaSourceConfig = object : MangaSourceConfig {
        override fun <T> get(key: ConfigKey<T>): T = key.defaultValue
    }

    override fun getDefaultUserAgent(): String =
        "Mozilla/5.0 (X11; Linux x86_64) CompatibilityFarm/1.0"

    override fun redrawImageResponse(response: Response, redraw: (Bitmap) -> Bitmap): Response =
        error("Image redraw is not exercised by this parser harness")

    override fun createBitmap(width: Int, height: Int): Bitmap =
        error("Bitmap creation is not exercised by this parser harness")
}
