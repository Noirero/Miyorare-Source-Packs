package compatibilityfarm

import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import tsuki.MangaLoaderContext
import tsuki.MangaParser
import tsuki.model.MangaListFilter
import tsuki.model.SortOrder

private suspend fun exerciseA2ApprovedLiveParser(fqcn: String) {
    val type = Class.forName(fqcn)
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

internal class AutoLive_gekkoushi_7f55937f4599 {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.guya.en.Danke")
    }
}

internal class AutoLive_gekkoushi_e18b80336c95 {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.en.DemonicScans")
    }
}

internal class AutoLive_gekkoushi_469ad680679d {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.mangareader.en.EnThunderScans")
    }
}

internal class AutoLive_gekkoushi_6f08c05f0fca {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.madara.en.GdScans")
    }
}

internal class AutoLive_gekkoushi_8bb4ddb43b1b {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.keyoapp.en.SuryaScans")
    }
}

internal class AutoLive_gekkoushi_2b0cf25c62bd {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.madara.en.Grabber")
    }
}

internal class AutoLive_gekkoushi_a7ec42449513 {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.guya.en.GuyaCubari")
    }
}

internal class AutoLive_gekkoushi_179e1a30e5cf {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.mangareader.en.Hentai20")
    }
}

internal class AutoLive_gekkoushi_0010cbcdcf06 {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.en.Hentai2Read")
    }
}

internal class AutoLive_gekkoushi_b2327ca45d13 {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.mangareader.id.KomikIndo")
    }
}

internal class AutoLive_gekkoushi_52e43af61de9 {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.mangareader.id.KomikLokalParser")
    }
}

internal class AutoLive_gekkoushi_f7a1b55b0440 {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.mangareader.id.Komiku")
    }
}

internal class AutoLive_gekkoushi_32c770fd5cd6 {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.zmanga.id.MaidId")
    }
}

internal class AutoLive_gekkoushi_e6501e959286 {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.mangareader.id.MangaSusuku")
    }
}

internal class AutoLive_gekkoushi_b1577ce9c3db {
    @Test
    fun browseDetailsChaptersAndPagesExecuteRealParserCode() = runBlocking {
        exerciseA2ApprovedLiveParser("tsuki.site.mangareader.id.ManhwaListOrg")
    }
}
