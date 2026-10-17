package compatibilityfarm

import java.util.concurrent.TimeUnit
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Response
import tsuki.MangaLoaderContext
import tsuki.MangaParser
import tsuki.bitmap.Bitmap
import tsuki.config.ConfigKey
import tsuki.config.MangaSourceConfig
import tsuki.model.MangaSource

internal class LiveMangaLoaderContext : MangaLoaderContext() {
    private val cookies = mutableListOf<Cookie>()

    override val cookieJar: CookieJar = object : CookieJar {
        override fun saveFromResponse(url: HttpUrl, incoming: List<Cookie>) {
            incoming.forEach { cookie ->
                cookies.removeAll { it.name == cookie.name && it.domain == cookie.domain && it.path == cookie.path }
                cookies += cookie
            }
        }
        override fun loadForRequest(url: HttpUrl): List<Cookie> = cookies.filter { it.matches(url) }
    }

    override val httpClient: OkHttpClient = OkHttpClient.Builder()
        .cookieJar(cookieJar)
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS)
        .callTimeout(35, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    override fun newParserInstance(source: MangaSource): MangaParser = error("not used by live onboarding harness")
    override fun getParserSources(): List<MangaSource> = emptyList()

    @Deprecated("Provide a base url")
    override suspend fun evaluateJs(script: String): String? = null
    override suspend fun evaluateJs(baseUrl: String, script: String): String? = null

    override fun getConfig(source: MangaSource): MangaSourceConfig = object : MangaSourceConfig {
        override fun <T> get(key: ConfigKey<T>): T = key.defaultValue
    }

    override fun getDefaultUserAgent(): String =
        "Mozilla/5.0 (X11; Linux x86_64) MiyorareCompatibilityFarm/1.0"

    override fun redrawImageResponse(response: Response, redraw: (Bitmap) -> Bitmap): Response = response
    override fun createBitmap(width: Int, height: Int): Bitmap = error("bitmap creation not used by parser smoke")
}
