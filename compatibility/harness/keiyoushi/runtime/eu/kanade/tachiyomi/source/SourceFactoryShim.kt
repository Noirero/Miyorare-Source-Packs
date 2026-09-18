package eu.kanade.tachiyomi.source

/**
 * Test-only minimal host interfaces required by Keiyoushi generated factories.
 *
 * Upstream extensions compile against Mihon host interfaces that are compileOnly
 * dependencies. Compatibility Farm supplies the binary surface at test runtime
 * without changing extension source behavior.
 */
@Suppress("unused")
interface Source {
    val id: Long
    val name: String
    val lang: String
}

@Suppress("unused")
interface SourceFactory {
    fun createSources(): List<Source>
}
