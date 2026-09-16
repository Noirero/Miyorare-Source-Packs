package com.noirero.miyorare.sourcelab

/**
 * Keeps the short-lived owner authorization only for the lifetime of the app
 * process. No OAuth token or backend proof is persisted to disk.
 */
internal object SourceLabOwnerSessionStore {
    @Volatile
    private var session: OwnerAccessSession? = null

    fun set(value: OwnerAccessSession?) {
        session = value
    }

    fun get(): OwnerAccessSession? {
        val current = session ?: return null
        return if (SourceLabAccessPolicy.evaluate(current).canControl) {
            current
        } else {
            session = null
            null
        }
    }

    fun clear() {
        session = null
    }
}
