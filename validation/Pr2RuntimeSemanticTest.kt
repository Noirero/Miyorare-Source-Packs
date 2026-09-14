package org.koitharu.kotatsu.tsuki

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koitharu.kotatsu.core.cache.MemoryContentCache
import org.koitharu.kotatsu.parsers.model.MangaListFilter
import org.koitharu.kotatsu.tsuki.model.TsukiMangaSource
import org.koitharu.kotatsu.tsuki.model.TsukiPluginDescriptor
import org.koitharu.kotatsu.tsuki.model.TsukiPluginProvider
import org.koitharu.kotatsu.tsuki.runtime.TsukiPluginRuntime
import java.io.File
import javax.inject.Inject

/**
 * Release-candidate validation only. This file lives outside the Miyorare application repository
 * and is injected into androidTest by the Source-Packs validation workflow.
 *
 * It proves two different things:
 *  1. every exposed source in every candidate shard can be instantiated by the real Miyorare
 *     Tsuki runtime (ABI/linkage/parser-construction smoke), and
 *  2. a small public representative set crosses the live semantic path list -> details -> pages.
 */
@HiltAndroidTest
@RunWith(AndroidJUnit4::class)
class Pr2RuntimeSemanticTest {

    @get:Rule
    var hiltRule = HiltAndroidRule(this)

    @Inject
    lateinit var pluginManager: TsukiPluginManager

    @Inject
    lateinit var runtime: TsukiPluginRuntime

    @Inject
    lateinit var contentCache: MemoryContentCache

    private val installed = mutableListOf<TsukiPluginDescriptor>()

    @Before
    fun setUp() {
        hiltRule.inject()
        pluginManager.getPlugins()
            .filter { it.provider == TsukiPluginProvider.MIYORARE }
            .forEach { pluginManager.remove(it.provider, it.pluginId) }
        installed.clear()
        installCandidateShards()
    }

    @Test
    fun allCandidateSourcesLoadAndRepresentativeSourcesWorkEndToEnd() = runBlocking {
        var parserCount = 0
        for (plugin in installed) {
            assertFalse("${plugin.pluginId} exposes no sources", plugin.sources.isEmpty())
            for (descriptor in plugin.sources) {
                if (descriptor.isBroken) continue
                val source = TsukiMangaSource(plugin, descriptor)
                val handle = runtime.getHandle(source)
                assertEquals(descriptor.name, handle.rawSource.name)
                assertEquals(descriptor.name, handle.parser.source.name)
                parserCount++
            }
        }
        assertTrue("Candidate pack exposed no loadable parsers", parserCount > 0)

        validateLiveChain(source("miyorare-id", "KOMIKU"), "one piece")
        validateLiveChain(source("miyorare-en", "MANGAPILL"), "one piece")
        validateLiveChain(source("miyorare-global", "GELBOORU"), "rating:general")
    }

    private fun installCandidateShards() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val assetContext = instrumentation.context
        val targetContext = instrumentation.targetContext
        val names = assetContext.assets.list(ASSET_DIR).orEmpty().toSet()
        assertEquals(EXPECTED_SHARDS.keys, names)

        EXPECTED_SHARDS.forEach { (assetName, pluginId) ->
            val staged = File(targetContext.cacheDir, "runtime-validation-$assetName")
            assetContext.assets.open("$ASSET_DIR/$assetName").use { input ->
                staged.outputStream().use(input::copyTo)
            }
            try {
                installed += pluginManager.installLocalJar(
                    sourceFile = staged,
                    request = TsukiPluginManager.InstallRequest(
                        pluginId = pluginId,
                        displayName = "PR2 runtime validation / $pluginId",
                        provider = TsukiPluginProvider.MIYORARE,
                        origin = "validation://source-packs-pr2",
                        version = "pr2-4ba0b0aa",
                    ),
                )
            } finally {
                staged.delete()
            }
        }
        assertEquals(EXPECTED_SHARDS.size, installed.size)
    }

    private fun source(pluginId: String, sourceName: String): TsukiMangaSource {
        val plugin = installed.firstOrNull { it.pluginId == pluginId }
            ?: error("Missing candidate shard $pluginId")
        val descriptor = plugin.sources.firstOrNull { it.name == sourceName && !it.isBroken }
            ?: error("$pluginId does not expose usable source $sourceName")
        return TsukiMangaSource(plugin, descriptor)
    }

    private suspend fun validateLiveChain(source: TsukiMangaSource, query: String) {
        var lastFailure: Throwable? = null
        repeat(2) { attempt ->
            try {
                withTimeout(60_000L) {
                    val repository = TsukiMangaRepository(
                        source = source,
                        cache = contentCache,
                        context = InstrumentationRegistry.getInstrumentation().targetContext,
                        runtime = runtime,
                    )
                    val list = repository.getList(
                        offset = 0,
                        order = null,
                        filter = MangaListFilter(query = query),
                    )
                    check(list.isNotEmpty()) { "${source.name}: live list/search returned no items" }

                    val details = repository.getDetails(list.first())
                    val chapter = details.chapters?.firstOrNull()
                        ?: error("${source.name}: details returned no chapters")
                    val pages = repository.getPages(chapter)
                    check(pages.isNotEmpty()) { "${source.name}: chapter returned no pages" }
                    val pageUrl = repository.getPageUrl(pages.first())
                    check(pageUrl.startsWith("https://") || pageUrl.startsWith("http://")) {
                        "${source.name}: invalid page URL: $pageUrl"
                    }
                }
                return
            } catch (error: Throwable) {
                lastFailure = error
                if (attempt == 0) delay(2_000L)
            }
        }
        throw AssertionError("${source.name}: live semantic chain failed after retry", lastFailure)
    }

    private companion object {
        const val ASSET_DIR = "runtime-packs"

        val EXPECTED_SHARDS = linkedMapOf(
            "miyorare-id-uma.jar" to "miyorare-id",
            "miyorare-id-gekkoushi.jar" to "miyorare-id-gekkoushi",
            "miyorare-en-uma.jar" to "miyorare-en",
            "miyorare-en-gekkoushi.jar" to "miyorare-en-gekkoushi",
            "miyorare-global-gekkoushi.jar" to "miyorare-global",
        )
    }
}
