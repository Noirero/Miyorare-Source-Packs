package com.noirero.miyorare.sourcelab

/**
 * Volatile process-local owner session.
 *
 * The GitHub user access token is intentionally never written to SharedPreferences, files,
 * databases, logs, savedInstanceState, or Android backups. Process death returns Source Lab to
 * public-viewer mode and requires owner verification again.
 */
internal data class OwnerRuntimeSession(
    val accessToken: String,
    val access: OwnerAccessSession,
    val backendAuthorizationRunId: Long,
)

internal object OwnerSessionStore {
    @Volatile
    private var value: OwnerRuntimeSession? = null

    fun set(session: OwnerRuntimeSession) {
        value = session
    }

    fun get(): OwnerRuntimeSession? = value

    fun clear() {
        value = null
    }
}
