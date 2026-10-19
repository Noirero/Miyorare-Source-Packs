package compatibilityfarm

import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import keiyoushi.source.KeiSource
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.lang.reflect.Method
import java.util.concurrent.TimeUnit

class AutoLive_keiyoushi_35572e9c39d8 {
    private val source: Any by lazy {
        val generated = Class.forName("keiyoushi.source.Generated")
        val instance = generated.getDeclaredConstructor().apply { isAccessible = true }.newInstance()
        val createSources = findMethodOrNull(instance, "createSources", emptyArray())
        if (createSources == null) {
            instance
        } else {
            createSources.isAccessible = true
            val sources = createSources.invoke(instance) as? List<*>
                ?: error("createSources did not return a list")
            sources.firstOrNull() ?: error("createSources returned no sources")
        }
    }
    private val client = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .callTimeout(35, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        val actual = source
        if (actual is KeiSource) {
            val popular = actual.getPopularManga(1)
            assertFalse("live browse returned no manga", popular.mangas.isEmpty())
            val manga = popular.mangas.first()

            val update = actual.fetchMangaUpdate(
                manga = manga,
                chapters = emptyList(),
                fetchDetails = true,
                fetchChapters = true,
            )
            assertTrue("details title is blank", update.manga.title.isNotBlank())
            assertFalse("details returned no chapters", update.chapters.isEmpty())

            val pages = actual.getPageList(update.chapters.first())
            assertFalse("first chapter returned no pages", pages.isEmpty())
        } else {
            val popularRequest = call("popularMangaRequest", arrayOf(Int::class.javaPrimitiveType!!), 1) as Request
            val popular = execute(popularRequest) { response ->
                call("popularMangaParse", arrayOf(Response::class.java), response) as MangasPage
            }
            assertFalse("live browse returned no manga", popular.mangas.isEmpty())
            val manga = popular.mangas.first()

            val detailsRequest = call("mangaDetailsRequest", arrayOf(SManga::class.java), manga) as Request
            val details = execute(detailsRequest) { response ->
                call("mangaDetailsParse", arrayOf(Response::class.java), response) as SManga
            }
            assertTrue("details title is blank", details.title.isNotBlank())
            if (details.url.isBlank()) details.url = manga.url

            val chapterRequest = call("chapterListRequest", arrayOf(SManga::class.java), details) as Request
            val chapters = execute(chapterRequest) { response ->
                @Suppress("UNCHECKED_CAST")
                call("chapterListParse", arrayOf(Response::class.java), response) as List<SChapter>
            }
            assertFalse("details returned no chapters", chapters.isEmpty())

            val pageRequest = call("pageListRequest", arrayOf(SChapter::class.java), chapters.first()) as Request
            val pages = execute(pageRequest) { response ->
                call("pageListParse", arrayOf(Response::class.java), response) as List<*>
            }
            assertFalse("first chapter returned no pages", pages.isEmpty())
        }
    }

    private fun <T> execute(request: Request, parser: (Response) -> T): T =
        client.newCall(request).execute().use { response ->
            check(response.code < 500) { "HTTP ${response.code} for ${request.url}" }
            parser(response)
        }

    private fun call(name: String, parameterTypes: Array<Class<*>>, vararg args: Any?): Any? {
        val method = findMethod(name, parameterTypes)
        method.isAccessible = true
        return method.invoke(source, *args)
    }

    private fun findMethod(name: String, parameterTypes: Array<Class<*>>): Method =
        findMethodOrNull(source, name, parameterTypes)
            ?: error("Method $name not found on ${source.javaClass.name}")

    private fun findMethodOrNull(target: Any, name: String, parameterTypes: Array<Class<*>>): Method? {
        var type: Class<*>? = target.javaClass
        while (type != null) {
            try {
                return type.getDeclaredMethod(name, *parameterTypes)
            } catch (_: NoSuchMethodException) {
                type = type.superclass
            }
        }
        return null
    }
}
