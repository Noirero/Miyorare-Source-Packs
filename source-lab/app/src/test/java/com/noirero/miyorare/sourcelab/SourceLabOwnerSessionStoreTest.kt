package com.noirero.miyorare.sourcelab

import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SourceLabOwnerSessionStoreTest {
    @After
    fun cleanup() {
        SourceLabOwnerSessionStore.clear()
    }

    @Test
    fun explicitViewerModeBlocksSavedOwnerSessionUntilOwnerIsSetAgain() {
        val session = validOwnerSession()
        SourceLabOwnerSessionStore.set(session)
        assertNotNull(SourceLabOwnerSessionStore.get())

        SourceLabOwnerSessionStore.enterViewerMode()
        assertTrue(SourceLabOwnerSessionStore.isViewerModeRequested())
        assertNull(SourceLabOwnerSessionStore.get())

        SourceLabOwnerSessionStore.set(session)
        assertFalse(SourceLabOwnerSessionStore.isViewerModeRequested())
        assertNotNull(SourceLabOwnerSessionStore.get())
    }

    private fun validOwnerSession() = OwnerAccessSession(
        authenticated = true,
        githubUserId = SourceLabAccessPolicy.ownerGithubUserId,
        githubAppId = SourceLabAccessPolicy.githubAppId,
        installationId = SourceLabAccessPolicy.installationId,
        repository = SourceLabAccessPolicy.repository,
        repositoryPermission = SourceLabAccessPolicy.minimumRepositoryPermission,
        backendAuthorized = true,
        backendAuthorizationExpiresAtEpochSeconds = System.currentTimeMillis() / 1000L + 300L,
        backendCapabilities = setOf(SourceLabControlAction.RUN_FARM),
    )
}
