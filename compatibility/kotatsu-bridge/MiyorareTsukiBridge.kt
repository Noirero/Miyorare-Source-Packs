@file:Suppress("DEPRECATION")
@file:OptIn(miyorare.kotatsuredo.InternalParsersApi::class, tsuki.InternalParsersApi::class)

package miyorare.kotatsuredo.bridge

import okhttp3.Interceptor
import okhttp3.Response
import miyorare.kotatsuredo.MangaLoaderContext as KContext
import miyorare.kotatsuredo.MangaParser as KParser
import miyorare.kotatsuredo.MangaParserAuthProvider as KAuth
import miyorare.kotatsuredo.bitmap.Bitmap as KBitmap
import miyorare.kotatsuredo.bitmap.Rect as KRect
import miyorare.kotatsuredo.config.ConfigKey as KConfigKey
import miyorare.kotatsuredo.config.MangaSourceConfig as KSourceConfig
import miyorare.kotatsuredo.model.ContentRating as KContentRating
import miyorare.kotatsuredo.model.ContentType as KContentType
import miyorare.kotatsuredo.model.Demographic as KDemographic
import miyorare.kotatsuredo.model.Favicon as KFavicon
import miyorare.kotatsuredo.model.Favicons as KFavicons
import miyorare.kotatsuredo.model.Manga as KManga
import miyorare.kotatsuredo.model.MangaChapter as KChapter
import miyorare.kotatsuredo.model.MangaListFilter as KFilter
import miyorare.kotatsuredo.model.MangaListFilterCapabilities as KFilterCapabilities
import miyorare.kotatsuredo.model.MangaListFilterOptions as KFilterOptions
import miyorare.kotatsuredo.model.MangaPage as KPage
import miyorare.kotatsuredo.model.MangaParserSource as KParserSource
import miyorare.kotatsuredo.model.MangaSource as KSource
import miyorare.kotatsuredo.model.MangaState as KState
import miyorare.kotatsuredo.model.MangaTag as KTag
import miyorare.kotatsuredo.model.SortOrder as KSortOrder
import miyorare.kotatsuredo.newParser
import tsuki.MangaLoaderContext as TContext
import tsuki.MangaParser as TParser
import tsuki.MangaParserAuthProvider as TAuth
import tsuki.bitmap.Bitmap as TBitmap
import tsuki.bitmap.Rect as TRect
import tsuki.config.ConfigKey as TConfigKey
import tsuki.config.MangaSourceConfig as TSourceConfig
import tsuki.model.ContentRating as TContentRating
import tsuki.model.ContentType as TContentType
import tsuki.model.Demographic as TDemographic
import tsuki.model.Favicon as TFavicon
import tsuki.model.Favicons as TFavicons
import tsuki.model.Manga as TManga
import tsuki.model.MangaChapter as TChapter
import tsuki.model.MangaListFilter as TFilter
import tsuki.model.MangaListFilterCapabilities as TFilterCapabilities
import tsuki.model.MangaListFilterOptions as TFilterOptions
import tsuki.model.MangaPage as TPage
import tsuki.model.MangaParserSource as TParserSource
import tsuki.model.MangaSource as TSource
import tsuki.model.MangaState as TState
import tsuki.model.MangaTag as TTag
import tsuki.model.SortOrder as TSortOrder
import tsuki.model.search.MangaSearchQuery as TSearchQuery
import tsuki.model.search.MangaSearchQueryCapabilities as TSearchCapabilities
import tsuki.util.LinkResolver as TLinkResolver
import java.util.EnumSet

/** Public entry used by the generated `tsuki.MangaParserFactoryKt`. */
public fun newAdapterParser(sourceName: String, host: TContext): TParser {
    val facade = TParserSource.valueOf(sourceName)
    val internalSource = KParserSource.valueOf(sourceName)
    val context = KotatsuContextAdapter(host)
    val delegate = internalSource.newParser(context)
    return KotatsuParserAdapter(delegate, context, facade)
}

private class KotatsuParserAdapter(
    private val delegate: KParser,
    private val bridgeContext: KotatsuContextAdapter,
    private val facadeSource: TParserSource,
) : TParser {

    override val source: TSource
        get() = facadeSource

    override val availableSortOrders: Set<TSortOrder>
        get() = delegate.availableSortOrders.mapTo(linkedSetOf()) { TSortOrder.valueOf(it.name) }

    override val searchQueryCapabilities: TSearchCapabilities = TSearchCapabilities()

    override val filterCapabilities: TFilterCapabilities
        get() = delegate.filterCapabilities.toTsuki()

    override val config: TSourceConfig
        get() = bridgeContext.hostConfig(facadeSource)

    override val authorizationProvider: TAuth?
        get() = delegate.authorizationProvider?.let(::KotatsuAuthAdapter)

    override val configKeyDomain: TConfigKey.Domain
        get() = TConfigKey.Domain(*delegate.configKeyDomain.presetValues)

    override val domain: String
        get() = delegate.domain

    override suspend fun getList(query: TSearchQuery): List<TManga> {
        throw UnsupportedOperationException("Deprecated MangaSearchQuery API is not exposed by the Kotatsu provider bridge")
    }

    override suspend fun getList(offset: Int, order: TSortOrder, filter: TFilter): List<TManga> =
        delegate.getList(offset, KSortOrder.valueOf(order.name), filter.toKotatsu(delegate.source))
            .map { it.toTsuki(facadeSource) }

    override suspend fun getDetails(manga: TManga): TManga =
        delegate.getDetails(manga.toKotatsu(delegate.source)).toTsuki(facadeSource)

    override suspend fun getPages(chapter: TChapter): List<TPage> =
        delegate.getPages(chapter.toKotatsu(delegate.source)).map { it.toTsuki(facadeSource) }

    override suspend fun getPageUrl(page: TPage): String =
        delegate.getPageUrl(page.toKotatsu(delegate.source))

    override suspend fun getFilterOptions(): TFilterOptions =
        delegate.getFilterOptions().toTsuki(facadeSource)

    override suspend fun getFavicons(): TFavicons = delegate.getFavicons().toTsuki()

    override fun onCreateConfig(keys: MutableCollection<TConfigKey<*>>) {
        val modern = ArrayList<KConfigKey<*>>()
        delegate.onCreateConfig(modern)
        modern.mapNotNullTo(keys) { it.toTsukiOrNull() }
    }

    override suspend fun getRelatedManga(seed: TManga): List<TManga> =
        delegate.getRelatedManga(seed.toKotatsu(delegate.source)).map { it.toTsuki(facadeSource) }

    override fun getRequestHeaders() = delegate.getRequestHeaders()

    override suspend fun resolveLink(resolver: TLinkResolver, link: okhttp3.HttpUrl): TManga? =
        delegate.resolveLink(bridgeContext.newLinkResolver(link), link)?.toTsuki(facadeSource)

    override fun intercept(chain: Interceptor.Chain): Response = delegate.intercept(chain)
}

private class KotatsuAuthAdapter(private val delegate: KAuth) : TAuth {
    override val authUrl: String
        get() = delegate.authUrl

    override suspend fun isAuthorized(): Boolean = delegate.isAuthorized()

    override suspend fun getUsername(): String = delegate.getUsername()
}

private class KotatsuContextAdapter(
    private val host: TContext,
) : KContext() {

    override val httpClient
        get() = host.httpClient

    override val cookieJar
        get() = host.cookieJar

    fun hostConfig(source: TSource): TSourceConfig = host.getConfig(source)

    override suspend fun evaluateJs(script: String): String? = host.evaluateJs(script)

    override suspend fun evaluateJs(baseUrl: String, script: String, timeout: Long): String? =
        host.evaluateJs(baseUrl, script)

    override fun requestBrowserAction(parser: KParser, url: String): Nothing =
        host.requestBrowserAction(
            KotatsuParserAdapter(parser, this, TParserSource.valueOf(parser.source.name)),
            url,
        )

    override fun requestCloudflareVerification(parser: KParser, url: String): Nothing =
        requestBrowserAction(parser, url)

    override fun getConfig(source: KSource): KSourceConfig =
        KotatsuConfigAdapter(host.getConfig(TParserSource.valueOf(source.name)))

    override fun getDefaultUserAgent(): String = host.getDefaultUserAgent()

    override fun redrawImageResponse(response: Response, redraw: (KBitmap) -> KBitmap): Response =
        host.redrawImageResponse(response) { input ->
            val result = redraw(KotatsuBitmap(input))
            (result as? KotatsuBitmap)?.delegate
                ?: error("Kotatsu bridge image redraw must return a host-backed bitmap")
        }

    override fun createBitmap(width: Int, height: Int): KBitmap = KotatsuBitmap(host.createBitmap(width, height))
}

private class KotatsuBitmap(val delegate: TBitmap) : KBitmap {
    override val width: Int
        get() = delegate.width

    override val height: Int
        get() = delegate.height

    override fun drawBitmap(sourceBitmap: KBitmap, src: KRect, dst: KRect) {
        val source = (sourceBitmap as? KotatsuBitmap)?.delegate
            ?: error("Kotatsu bridge bitmap belongs to a different host")
        delegate.drawBitmap(
            source,
            TRect(src.left, src.top, src.right, src.bottom),
            TRect(dst.left, dst.top, dst.right, dst.bottom),
        )
    }
}

private class KotatsuConfigAdapter(private val host: TSourceConfig) : KSourceConfig {
    @Suppress("UNCHECKED_CAST")
    override fun <T> get(key: KConfigKey<T>): T = when (key) {
        is KConfigKey.Domain -> host[TConfigKey.Domain(*key.presetValues)]
        is KConfigKey.UserAgent -> host[TConfigKey.UserAgent(key.defaultValue)]
        is KConfigKey.ShowSuspiciousContent -> host[TConfigKey.ShowSuspiciousContent(key.defaultValue)]
        is KConfigKey.SplitByTranslations -> host[TConfigKey.SplitByTranslations(key.defaultValue)]
        is KConfigKey.PreferredImageServer -> host[
            TConfigKey.PreferredImageServer(key.presetValues, key.defaultValue),
        ]
        is KConfigKey.DisableUpdateChecking -> key.defaultValue
        is KConfigKey.InterceptCloudflare -> key.defaultValue
    } as T
}

private fun KConfigKey<*>.toTsukiOrNull(): TConfigKey<*>? = when (this) {
    is KConfigKey.Domain -> TConfigKey.Domain(*presetValues)
    is KConfigKey.UserAgent -> TConfigKey.UserAgent(defaultValue)
    is KConfigKey.ShowSuspiciousContent -> TConfigKey.ShowSuspiciousContent(defaultValue)
    is KConfigKey.SplitByTranslations -> TConfigKey.SplitByTranslations(defaultValue)
    is KConfigKey.PreferredImageServer -> TConfigKey.PreferredImageServer(presetValues, defaultValue)
    is KConfigKey.DisableUpdateChecking,
    is KConfigKey.InterceptCloudflare,
    -> null
}

private fun KFilterCapabilities.toTsuki() = TFilterCapabilities(
    isMultipleTagsSupported = isMultipleTagsSupported,
    isTagsExclusionSupported = isTagsExclusionSupported,
    isSearchSupported = isSearchSupported,
    isSearchWithFiltersSupported = isSearchWithFiltersSupported,
    isYearSupported = isYearSupported,
    isYearRangeSupported = isYearRangeSupported,
    isOriginalLocaleSupported = isOriginalLocaleSupported,
    isAuthorSearchSupported = isAuthorSearchSupported,
)

private fun TFilter.toKotatsu(source: KSource) = KFilter(
    query = query,
    tags = tags.mapTo(linkedSetOf()) { it.toKotatsu(source) },
    tagsExclude = tagsExclude.mapTo(linkedSetOf()) { it.toKotatsu(source) },
    locale = locale,
    originalLocale = originalLocale,
    states = states.mapTo(linkedSetOf()) { KState.valueOf(it.name) },
    contentRating = contentRating.mapTo(linkedSetOf()) { KContentRating.valueOf(it.name) },
    types = types.mapTo(linkedSetOf()) { KContentType.valueOf(it.name) },
    demographics = demographics.mapTo(linkedSetOf()) { KDemographic.valueOf(it.name) },
    year = year,
    yearFrom = yearFrom,
    yearTo = yearTo,
    author = author,
)

private fun KFilterOptions.toTsuki(source: TSource) = TFilterOptions(
    availableTags = availableTags.mapTo(linkedSetOf()) { it.toTsuki(source) },
    availableStates = availableStates.mapTo(linkedSetOf()) { TState.valueOf(it.name) },
    availableContentRating = availableContentRating.mapTo(linkedSetOf()) { TContentRating.valueOf(it.name) },
    availableContentTypes = availableContentTypes.mapTo(linkedSetOf()) { TContentType.valueOf(it.name) },
    availableDemographics = availableDemographics.mapTo(linkedSetOf()) { TDemographic.valueOf(it.name) },
    availableLocales = availableLocales,
)

private fun KTag.toTsuki(source: TSource) = TTag(title, key, source)
private fun TTag.toKotatsu(source: KSource) = KTag(title, key, source)

private fun KManga.toTsuki(source: TSource) = TManga(
    id = id,
    title = title,
    altTitles = altTitles,
    url = url,
    publicUrl = publicUrl,
    rating = rating,
    contentRating = contentRating?.let { TContentRating.valueOf(it.name) },
    coverUrl = coverUrl,
    tags = tags.mapTo(linkedSetOf()) { it.toTsuki(source) },
    state = state?.let { TState.valueOf(it.name) },
    authors = authors,
    largeCoverUrl = largeCoverUrl,
    description = description,
    chapters = chapters?.map { it.toTsuki(source) },
    source = source,
)

private fun TManga.toKotatsu(source: KSource) = KManga(
    id = id,
    title = title,
    altTitles = altTitles,
    url = url,
    publicUrl = publicUrl,
    rating = rating,
    contentRating = contentRating?.let { KContentRating.valueOf(it.name) },
    coverUrl = coverUrl,
    tags = tags.mapTo(linkedSetOf()) { it.toKotatsu(source) },
    state = state?.let { KState.valueOf(it.name) },
    authors = authors,
    largeCoverUrl = largeCoverUrl,
    description = description,
    chapters = chapters?.map { it.toKotatsu(source) },
    source = source,
)

private fun KChapter.toTsuki(source: TSource) = TChapter(
    id = id,
    title = title,
    number = number,
    volume = volume,
    url = url,
    scanlator = scanlator,
    uploadDate = uploadDate,
    branch = branch,
    source = source,
)

private fun TChapter.toKotatsu(source: KSource) = KChapter(
    id = id,
    title = title,
    number = number,
    volume = volume,
    url = url,
    scanlator = scanlator,
    uploadDate = uploadDate,
    branch = branch,
    source = source,
)

private fun KPage.toTsuki(source: TSource) = TPage(
    id = id,
    url = url,
    preview = preview,
    source = source,
)

private fun TPage.toKotatsu(source: KSource) = KPage(
    id = id,
    url = url,
    preview = preview,
    source = source,
)

private fun KFavicons.toTsuki() = TFavicons(
    favicons = map { TFavicon(it.url, it.size, null) },
    referer = referer,
)
