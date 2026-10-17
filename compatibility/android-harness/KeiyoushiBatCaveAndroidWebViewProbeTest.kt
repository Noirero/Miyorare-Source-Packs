package org.koitharu.kotatsu.p2

import android.webkit.CookieManager
import android.webkit.WebView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import eu.kanade.tachiyomi.source.Source
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koitharu.kotatsu.mihon.MihonExtensionLoader
import org.koitharu.kotatsu.mihon.model.MihonLoadResult
import java.io.File
import javax.inject.Inject

@HiltAndroidTest
@RunWith(AndroidJUnit4::class)
class KeiyoushiBatCaveAndroidWebViewProbeTest {

    @get:Rule
    var hiltRule = HiltAndroidRule(this)

    @Inject
    lateinit var extensionLoader: MihonExtensionLoader

    @Before
    fun setUp() {
        hiltRule.inject()
    }

    @Test
    fun probeExactBatCaveRuntime() {
        runBlocking {
            val instrumentation = InstrumentationRegistry.getInstrumentation()
            val testContext = instrumentation.context
            val context = instrumentation.targetContext
            val args = InstrumentationRegistry.getArguments()
            val candidate = requireNotNull(args.getString("p2Candidate"))
            val miyorareRevision = requireNotNull(args.getString("p2MiyorareRevision"))
            val workflowRunId = requireNotNull(args.getString("p2WorkflowRunId")).toLong()

            val providerUrl = "https://batcave.biz/"
            val providerHost = "batcave.biz"
            val evidenceFile = File(context.filesDir, "p2-batcave-evidence.json")
            val apkFile = File(context.cacheDir, "p2-batcave.apk")
            testContext.assets.open("p2/batcave.apk").use { input ->
                apkFile.outputStream().use(input::copyTo)
            }

            @Suppress("DEPRECATION")
            val archiveInfo = context.packageManager.getPackageArchiveInfo(apkFile.absolutePath, 0)
            val packageName = archiveInfo?.packageName.orEmpty()
            if (packageName.isNotEmpty()) {
                MihonExtensionLoader.uninstallPrivateExtension(context, packageName)
            }

            val cookieManager = CookieManager.getInstance()
            cookieManager.setAcceptCookie(true)
            cookieManager.setCookie(providerUrl, "__guard_trust=; Max-Age=0; Path=/")
            cookieManager.flush()

            val webViewPackage = WebView.getCurrentWebViewPackage()
            var installSucceeded = false
            var loadSucceeded = false
            var sourceName: String? = null
            var sourceRequestSucceeded = false
            var sourceResultCount = 0
            var error: String? = null

            try {
                installSucceeded = MihonExtensionLoader.installPrivateExtensionFile(
                    context = context,
                    file = apkFile,
                    replaceExistingProvider = true,
                    expectedPackageName = packageName.takeIf(String::isNotEmpty),
                )
                if (installSucceeded) {
                    val loaded = extensionLoader.loadExtensions(context, privateMode = true)
                    val success = loaded
                        .filterIsInstance<MihonLoadResult.Success>()
                        .firstOrNull { result -> result.sources.any { it.name == "BatCave" } }
                    val source: Source? = success?.sources?.firstOrNull { it.name == "BatCave" }
                    loadSucceeded = source != null
                    sourceName = source?.name
                    if (source != null) {
                        val page = withTimeout(90_000L) {
                            source.getPopularManga(1)
                        }
                        sourceResultCount = page.mangas.size
                        sourceRequestSucceeded = sourceResultCount > 0
                    }
                }
            } catch (t: Throwable) {
                error = "${t::class.java.name}: ${t.message.orEmpty()}"
            }

            val trustCookieValue = cookieManager.getCookie(providerUrl)
                .orEmpty()
                .split(';')
                .asSequence()
                .map(String::trim)
                .firstOrNull { it.startsWith("__guard_trust=") }
                ?.substringAfter('=', "")
                .orEmpty()
            val trustCookieObserved = trustCookieValue.isNotBlank()

            val webViewJson = JSONObject()
                .put("available", webViewPackage != null)
                .put("packageName", webViewPackage?.packageName ?: "")
                .put("versionName", webViewPackage?.versionName ?: "")
                .put("versionCode", webViewPackage?.longVersionCode ?: 0L)

            val evidence = JSONObject()
                .put("schema", 1)
                .put("canonicalId", "miyorare:miyorare-en:BATCAVE")
                .put("candidateRevision", candidate)
                .put("miyorareRevision", miyorareRevision)
                .put("workflowRunId", workflowRunId)
                .put("runtime", "miyorare-android-instrumentation")
                .put("providerHost", providerHost)
                .put("extensionPackageName", packageName)
                .put("extensionInstallSucceeded", installSucceeded)
                .put("extensionLoadSucceeded", loadSucceeded)
                .put("sourceName", sourceName ?: JSONObject.NULL)
                .put("sourceRequestSucceeded", sourceRequestSucceeded)
                .put("sourceResultCount", sourceResultCount)
                .put("dleGuardTrustCookieObserved", trustCookieObserved)
                .put("webView", webViewJson)
                .put("error", error ?: JSONObject.NULL)

            evidenceFile.writeText(evidence.toString(2) + "\n")

            if (packageName.isNotEmpty()) {
                MihonExtensionLoader.uninstallPrivateExtension(context, packageName)
            }
            apkFile.delete()
        }
    }
}
