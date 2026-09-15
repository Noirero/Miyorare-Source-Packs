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
    fun wrongGithubAppCannotControl() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(githubAppId = 1L))
        assertFalse(decision.canControl)
        assertEquals("GITHUB_APP_MISMATCH", decision.reason)
    }

    @Test
    fun wrongInstallationCannotControl() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(installationId = 1L))
        assertFalse(decision.canControl)
        assertEquals("INSTALLATION_MISMATCH", decision.reason)
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

    @Test
    fun publicDeviceFlowConfigMatchesAuthorizationPolicy() {
        assertEquals(SourceLabAccessPolicy.ownerGithubUserId, GitHubAppPublicConfig.ownerGithubUserId)
        assertEquals(SourceLabAccessPolicy.githubAppId, GitHubAppPublicConfig.appId)
        assertEquals(SourceLabAccessPolicy.installationId, GitHubAppPublicConfig.installationId)
        assertEquals(SourceLabAccessPolicy.repository, GitHubAppPublicConfig.repository)
        assertTrue(GitHubAppPublicConfig.clientId.isNotBlank())
    }

    private fun validSession(
        githubUserId: Long = SourceLabAccessPolicy.ownerGithubUserId,
        githubAppId: Long = SourceLabAccessPolicy.githubAppId,
        installationId: Long = SourceLabAccessPolicy.installationId,
        repository: String = SourceLabAccessPolicy.repository,
        repositoryPermission: String = "admin",
        backendAuthorized: Boolean = true,
    ) = OwnerAccessSession(
        authenticated = true,
        githubUserId = githubUserId,
        githubAppId = githubAppId,
        installationId = installationId,
        repository = repository,
        repositoryPermission = repositoryPermission,
        backendAuthorized = backendAuthorized,
    )
}
