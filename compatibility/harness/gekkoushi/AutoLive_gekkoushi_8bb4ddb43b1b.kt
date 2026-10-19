package compatibilityfarm

import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.MangaLoaderContext
import tsuki.MangaParser
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder

internal class AutoLive_gekkoushi_8bb4ddb43b1b {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        val type = Class.forName("tsuki.site.keyoapp.en.SuryaScans")
        val ctor = type.getDeclaredConstructor(MangaLoaderContext::class.java).apply { isAccessible = true }
        val parser = ctor.newInstance(LiveMangaLoaderContext()) as MangaParser

        var browse = emptyList<tsuki.model.Manga>()
        var lastFailure: Throwable? = null
        for (order in listOf(SortOrder.UPDATED, SortOrder.POPULARITY, SortOrder.NEWEST, SortOrder.ALPHABETICAL)) {
            try {
                val candidate = parser.getList(0, order, MangaListFilter())
                if (candidate.isNotEmpty()) {
                    browse = candidate
                    break
                }
            } catch (t: Throwable) {
                lastFailure = t
            }
        }
        assertTrue(browse.isNotEmpty(), "live browse returned no manga; lastFailure=${lastFailure?.javaClass?.simpleName}")

        val details = parser.getDetails(browse.first())
        assertTrue(details.title.isNotBlank(), "details title is blank")
        val chapters = details.chapters
        assertNotNull(chapters, "details returned null chapters")
        assertTrue(chapters!!.isNotEmpty(), "details returned no chapters")

        val pages = parser.getPages(chapters.first())
        assertTrue(pages.isNotEmpty(), "first chapter returned no pages")
        assertTrue(pages.first().url.isNotBlank(), "first page URL is blank")
    }
}
