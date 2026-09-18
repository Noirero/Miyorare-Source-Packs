package eu.kanade.tachiyomi.source.online

import eu.kanade.tachiyomi.network.NetworkHelper
import eu.kanade.tachiyomi.source.Source
import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import okhttp3.Headers
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * Test-only host shim for Keiyoushi extension bytecode.
 *
 * Keiyoushi's published extensions-lib intentionally contains throwing compile-time stubs;
 * the real host app provides these members at runtime. Compatibility Farm supplies only the
 * minimal host behavior required to execute the pinned source parser without modifying it.
 */
@Suppress("unused")
abstract class HttpSource : Source {
    protected val network: NetworkHelper = NetworkHelper()

    abstract override val name: String
    abstract override val lang: String
    abstract val baseUrl: String

    open val versionId: Int = 1
    override val id: Long = 0L

    // KeiSource replaces this delegate reflectively during initialization, matching the host app.
    val headers: Headers by lazy { headersBuilder().build() }

    open val client: OkHttpClient
        get() = network.client

    protected open fun headersBuilder(): Headers.Builder = Headers.Builder()

    fun SChapter.setUrlWithoutDomain(url: String) {
        this.url = withoutDomain(url)
    }

    fun SManga.setUrlWithoutDomain(url: String) {
        this.url = withoutDomain(url)
    }

    open fun getMangaUrl(manga: SManga): String = absoluteUrl(manga.url)

    open fun getChapterUrl(chapter: SChapter): String = absoluteUrl(chapter.url)

    open fun mangaDetailsRequest(manga: SManga): Request =
        Request.Builder().url(getMangaUrl(manga)).headers(headers).get().build()

    open fun chapterListRequest(manga: SManga): Request =
        Request.Builder().url(getMangaUrl(manga)).headers(headers).get().build()

    open fun pageListRequest(chapter: SChapter): Request =
        Request.Builder().url(getChapterUrl(chapter)).headers(headers).get().build()

    open fun getFilterList(): FilterList = FilterList()

    private fun absoluteUrl(value: String): String =
        if (value.startsWith("http://") || value.startsWith("https://")) value else baseUrl + value

    private fun withoutDomain(value: String): String {
        val parsed = value.toHttpUrlOrNull() ?: return value
        val query = parsed.encodedQuery
        return if (query.isNullOrEmpty()) parsed.encodedPath else "${parsed.encodedPath}?$query"
    }
}
