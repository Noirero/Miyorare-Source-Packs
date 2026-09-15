package compatibilityfarm

import android.app.Application
import android.content.SharedPreferences
import eu.kanade.tachiyomi.extension.en.asurascans.AsuraScans
import eu.kanade.tachiyomi.network.DeterministicNetwork
import eu.kanade.tachiyomi.network.DeterministicNetwork.FixtureResponse
import eu.kanade.tachiyomi.source.model.FilterList
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import uy.kohesive.injekt.Injekt
import uy.kohesive.injekt.api.addSingleton

class KeiyoushiAsuraScansParserHarnessTest {
    companion object {
        @JvmStatic
        @BeforeClass
        fun installHostServices() {
            Injekt.addSingleton(Json { ignoreUnknownKeys = true })
            val application: Application = TestApplication()
            Injekt.addSingleton(application)
        }
    }

    @Test
    fun executesPinnedAsuraApiAstroDetailsChaptersAndPages() = runBlocking {
        DeterministicNetwork.install { request ->
            val url = request.url
            when {
                request.method == "GET" && url.host == "api.asurascans.com" && url.encodedPath == "/api/series" -> FixtureResponse(
                    """
                    {
                      "data": [{
                        "public_url": "/comics/asura-fixture-abcd1234",
                        "slug": "asura-fixture",
                        "title": "Asura Fixture",
                        "coverUrl": "https://asurascans.com/covers/alpha.jpg"
                      }],
                      "meta": {"has_more": false}
                    }
                    """.trimIndent(),
                    "application/json; charset=utf-8",
                )
                request.method == "GET" && url.host == "asurascans.com" && url.encodedPath == "/comics/asura-fixture-abcd1234" -> FixtureResponse(
                    """
                    <html><body>
                      <div props='{"title":"Asura Fixture Detailed","coverUrl":"https://asurascans.com/covers/detail.jpg","author":"Fixture Author","artist":"Fixture Artist","description":"<p>Fixture Asura synopsis.</p>","type":"manhwa","genres":[{"name":"Action","slug":"action"}],"status":"ongoing"}'></div>
                      <div props='{"publicUrl":"/comics/asura-fixture-abcd1234","seriesSlug":"asura-fixture"}'></div>
                      <div props='{"chapters":[{"number":1.0,"title":"First Step","created_at":"2026-01-01T00:00:00Z","is_premium":false,"series_slug":"asura-fixture"}]}'></div>
                    </body></html>
                    """.trimIndent(),
                )
                request.method == "GET" && url.host == "asurascans.com" && url.encodedPath == "/comics/asura-fixture-abcd1234/chapter/1" -> FixtureResponse(
                    """
                    <html><body>
                      <div props='{"pages":[{"url":"https://asurascans.com/pages/001.jpg"},{"url":"https://asurascans.com/pages/002.jpg"}]}'></div>
                    </body></html>
                    """.trimIndent(),
                )
                else -> error("Unexpected Asura parser request: ${request.method} $url")
            }
        }

        try {
            val source = newSource()
            val browse = source.getPopularManga(1)
            assertFalse(browse.hasNextPage)
            assertEquals(1, browse.mangas.size)
            val manga = browse.mangas.single()
            assertEquals("Asura Fixture", manga.title)
            assertEquals("/series/asura-fixture", manga.url)

            val search = source.getSearchMangaList(1, "Asura", FilterList())
            assertEquals(1, search.mangas.size)

            val update = source.getMangaUpdate(
                manga = manga,
                chapters = emptyList(),
                fetchDetails = true,
                fetchChapters = true,
            )
            assertEquals("Asura Fixture Detailed", update.manga.title)
            assertEquals("Fixture Author", update.manga.author)
            assertEquals("Fixture Artist", update.manga.artist)
            assertTrue(update.manga.genre.orEmpty().contains("Action"))
            assertEquals(1, update.chapters.size)
            val chapter = update.chapters.single()
            assertEquals("Chapter 1 - First Step", chapter.name)
            assertTrue(chapter.date_upload > 0L)

            val pages = source.getPageList(chapter)
            assertEquals(2, pages.size)
            assertEquals("https://asurascans.com/pages/001.jpg", pages[0].imageUrl)
            assertEquals("https://asurascans.com/pages/002.jpg", pages[1].imageUrl)
        } finally {
            DeterministicNetwork.clear()
        }
    }

    private fun newSource(): AsuraScans {
        val generated = Class.forName("keiyoushi.source.Generated")
        return generated.getDeclaredConstructor().apply { isAccessible = true }.newInstance() as AsuraScans
    }
}

private class TestApplication : Application() {
    private val stores = mutableMapOf<String, SharedPreferences>()

    override fun getSharedPreferences(name: String?, mode: Int): SharedPreferences =
        stores.getOrPut(name.orEmpty()) { MemoryPreferences() }
}

private class MemoryPreferences : SharedPreferences {
    private val values = linkedMapOf<String, Any?>()
    private val listeners = linkedSetOf<SharedPreferences.OnSharedPreferenceChangeListener>()

    override fun getAll(): MutableMap<String, *> = HashMap(values)
    override fun getString(key: String?, defValue: String?): String? = values[key] as? String ?: defValue
    @Suppress("UNCHECKED_CAST")
    override fun getStringSet(key: String?, defValues: MutableSet<String>?): MutableSet<String>? =
        (values[key] as? Set<String>)?.toMutableSet() ?: defValues
    override fun getInt(key: String?, defValue: Int): Int = values[key] as? Int ?: defValue
    override fun getLong(key: String?, defValue: Long): Long = values[key] as? Long ?: defValue
    override fun getFloat(key: String?, defValue: Float): Float = values[key] as? Float ?: defValue
    override fun getBoolean(key: String?, defValue: Boolean): Boolean = values[key] as? Boolean ?: defValue
    override fun contains(key: String?): Boolean = values.containsKey(key)
    override fun edit(): SharedPreferences.Editor = Editor()
    override fun registerOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {
        if (listener != null) listeners += listener
    }
    override fun unregisterOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {
        if (listener != null) listeners -= listener
    }

    private inner class Editor : SharedPreferences.Editor {
        private val updates = linkedMapOf<String, Any?>()
        private val removals = linkedSetOf<String>()
        private var clear = false

        override fun putString(key: String?, value: String?): SharedPreferences.Editor = apply { updates[key.orEmpty()] = value }
        override fun putStringSet(key: String?, values: MutableSet<String>?): SharedPreferences.Editor = apply { updates[key.orEmpty()] = values?.toSet() }
        override fun putInt(key: String?, value: Int): SharedPreferences.Editor = apply { updates[key.orEmpty()] = value }
        override fun putLong(key: String?, value: Long): SharedPreferences.Editor = apply { updates[key.orEmpty()] = value }
        override fun putFloat(key: String?, value: Float): SharedPreferences.Editor = apply { updates[key.orEmpty()] = value }
        override fun putBoolean(key: String?, value: Boolean): SharedPreferences.Editor = apply { updates[key.orEmpty()] = value }
        override fun remove(key: String?): SharedPreferences.Editor = apply { removals += key.orEmpty() }
        override fun clear(): SharedPreferences.Editor = apply { clear = true }
        override fun commit(): Boolean { applyChanges(); return true }
        override fun apply() { applyChanges() }

        private fun applyChanges() {
            val changed = linkedSetOf<String>()
            if (clear) {
                changed += values.keys
                values.clear()
            }
            removals.forEach { key -> if (values.remove(key) != null) changed += key }
            updates.forEach { (key, value) ->
                if (value == null) values.remove(key) else values[key] = value
                changed += key
            }
            changed.forEach { key -> listeners.forEach { it.onSharedPreferenceChanged(this@MemoryPreferences, key) } }
        }
    }
}
