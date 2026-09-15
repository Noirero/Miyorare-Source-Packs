package com.noirero.miyorare.sourcelab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccessControlTest {
    @Test
    fun unauthenticatedUserIsPublicViewer() {
        val decision = SourceLabAccessPolicy.evaluate(null)
        assertEquals(SourceLabRole.PUBLIC_VIEWER, decision.role)
        assertFalse(decision.canControl)
        assertEquals("PUBLIC_VIEWER", decision.reason)
    }

    @Test
    fun differentGithubUserCannotControl() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(githubUserId = 42L))
        assertFalse(decision.canControl)
        assertEquals("OWNER_ID_MISMATCH", decision.reason)
    }

    @Test
    fun ownerWithoutAdminPermissionCannotControl() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(repositoryPermission = "push"))
        assertFalse(decision.canControl)
        assertEquals("INSUFFICIENT_REPOSITORY_PERMISSION", decision.reason)
    }

    @Test
    fun ownerWithoutBackendAuthorizationCannotControl() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(backendAuthorized = false))
        assertFalse(decision.canControl)
        assertEquals("BACKEND_AUTHORIZATION_REQUIRED", decision.reason)
    }

    @Test
    fun exactOwnerWithBackendAuthorizationCanControl() {
        val session = validSession()
        val decision = SourceLabAccessPolicy.evaluate(session)
        assertEquals(SourceLabRole.OWNER_AUTHENTICATED, decision.role)
        assertTrue(decision.canControl)
        SourceLabControlAction.entries.forEach { action ->
            assertTrue(SourceLabAccessPolicy.canPerform(action, session))
        }
    }

    @Test
    fun repositoryMismatchFailsClosed() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(repository = "Noirero/Other"))
        assertFalse(decision.canControl)
        assertEquals("REPOSITORY_MISMATCH", decision.reason)
    }

    private fun validSession(
        githubUserId: Long = SourceLabAccessPolicy.ownerGithubUserId,
        repository: String = SourceLabAccessPolicy.repository,
        repositoryPermission: String = "admin",
        backendAuthorized: Boolean = true,
    ) = OwnerAccessSession(
        authenticated = true,
        githubUserId = githubUserId,
        repository = repository,
        repositoryPermission = repositoryPermission,
        backendAuthorized = backendAuthorized,
    )
}
