package com.noirero.miyorare.sourcelab

/**
 * Keeps the short-lived owner authorization only for the lifetime of the app
 * process. No OAuth token or backend proof is persisted to disk.
 *
 * Viewer mode is also process-local. Once the user explicitly chooses Viewer,
 * background/read-only screens must not silently restore a saved Owner
 * credential. Owner mode can be re-entered explicitly through the gate.
 */
internal object SourceLabOwnerSessionStore {
    @Volatile
    private var session: OwnerAccessSession? = null

    @Volatile
    private var viewerModeRequested: Boolean = false

    fun set(value: OwnerAccessSession?) {
        session = value
        if (value != null) {
            viewerModeRequested = false
        }
    }

    fun get(): OwnerAccessSession? {
        if (viewerModeRequested) return null
        val current = session ?: return null
        return if (SourceLabAccessPolicy.evaluate(current).canControl) {
            current
        } else {
            session = null
            null
        }
    }

    fun enterViewerMode() {
        session = null
        viewerModeRequested = true
    }

    fun isViewerModeRequested(): Boolean = viewerModeRequested

    fun clear() {
        session = null
        viewerModeRequested = false
    }
}
