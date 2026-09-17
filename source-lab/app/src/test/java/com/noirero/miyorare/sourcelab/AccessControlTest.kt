package com.noirero.miyorare.sourcelab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccessControlTest {
    private val now = 1_800_000_000L

    @Test
    fun unauthenticatedUserIsPublicViewer() {
        val decision = SourceLabAccessPolicy.evaluate(null, now)
        assertEquals(SourceLabRole.PUBLIC_VIEWER, decision.role)
        assertFalse(decision.canControl)
        assertEquals("PUBLIC_VIEWER", decision.reason)
    }

    @Test
    fun differentGithubUserCannotControl() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(githubUserId = 42L), now)
        assertFalse(decision.canControl)
        assertEquals("OWNER_ID_MISMATCH", decision.reason)
    }

    @Test
    fun wrongGithubAppCannotControl() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(githubAppId = 1L), now)
        assertFalse(decision.canControl)
        assertEquals("GITHUB_APP_MISMATCH", decision.reason)
    }

    @Test
    fun wrongInstallationCannotControl() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(installationId = 1L), now)
        assertFalse(decision.canControl)
        assertEquals("INSTALLATION_MISMATCH", decision.reason)
    }

    @Test
    fun ownerWithoutAdminPermissionCannotControl() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(repositoryPermission = "push"), now)
        assertFalse(decision.canControl)
        assertEquals("INSUFFICIENT_REPOSITORY_PERMISSION", decision.reason)
    }

    @Test
    fun ownerWithoutBackendAuthorizationCannotControl() {
        val decision = SourceLabAccessPolicy.evaluate(validSession(backendAuthorized = false), now)
        assertFalse(decision.canControl)
        assertEquals("BACKEND_AUTHORIZATION_REQUIRED", decision.reason)
    }

    @Test
    fun expiredBackendAuthorizationFailsClosed() {
        val decision = SourceLabAccessPolicy.evaluate(
            validSession(expiresAt = now),
            now,
        )
        assertFalse(decision.canControl)
        assertEquals("BACKEND_AUTHORIZATION_EXPIRED", decision.reason)
    }

    @Test
    fun backendAuthorizedOwnerIsRecognizedButGetsNoImplicitWriteCapability() {
        val session = validSession()
        val decision = SourceLabAccessPolicy.evaluate(session, now)
        assertEquals(SourceLabRole.OWNER_AUTHENTICATED, decision.role)
        assertTrue(decision.canControl)
        SourceLabControlAction.entries.forEach { action ->
            assertFalse(SourceLabAccessPolicy.canPerform(action, session, now))
        }
    }

    @Test
    fun onlyExplicitBackendCapabilityCanBePerformed() {
        val session = validSession(
            capabilities = setOf(SourceLabControlAction.RUN_FARM),
        )
        assertTrue(SourceLabAccessPolicy.canPerform(SourceLabControlAction.RUN_FARM, session, now))
        assertFalse(SourceLabAccessPolicy.canPerform(SourceLabControlAction.APPROVE, session, now))
        assertFalse(SourceLabAccessPolicy.canPerform(SourceLabControlAction.PROMOTE, session, now))
        assertFalse(SourceLabAccessPolicy.canPerform(SourceLabControlAction.SIGN, session, now))
        assertFalse(SourceLabAccessPolicy.canPerform(SourceLabControlAction.PUBLISH, session, now))
        assertFalse(SourceLabAccessPolicy.canPerform(SourceLabControlAction.ADD_TO_FARM, session, now))
    }

    @Test
    fun addToFarmRequiresItsOwnExplicitCapability() {
        val session = validSession(
            capabilities = setOf(SourceLabControlAction.ADD_TO_FARM),
        )
        assertTrue(SourceLabAccessPolicy.canPerform(SourceLabControlAction.ADD_TO_FARM, session, now))
        assertFalse(SourceLabAccessPolicy.canPerform(SourceLabControlAction.RUN_FARM, session, now))
        assertFalse(SourceLabAccessPolicy.canPerform(SourceLabControlAction.APPROVE, session, now))
    }

    @Test
    fun repositoryMismatchFailsClosed() {
        val decision = SourceLabAccessPolicy.evaluate(
            validSession(repository = "Noirero/Other"),
            now,
        )
        assertFalse(decision.canControl)
        assertEquals("REPOSITORY_MISMATCH", decision.reason)
    }

    private fun validSession(
        githubUserId: Long = SourceLabAccessPolicy.ownerGithubUserId,
        githubAppId: Long = SourceLabAccessPolicy.githubAppId,
        installationId: Long = SourceLabAccessPolicy.installationId,
        repository: String = SourceLabAccessPolicy.repository,
        repositoryPermission: String = "admin",
        backendAuthorized: Boolean = true,
        expiresAt: Long = now + 300L,
        capabilities: Set<SourceLabControlAction> = emptySet(),
    ) = OwnerAccessSession(
        authenticated = true,
        githubUserId = githubUserId,
        githubAppId = githubAppId,
        installationId = installationId,
        repository = repository,
        repositoryPermission = repositoryPermission,
        backendAuthorized = backendAuthorized,
        backendAuthorizationExpiresAtEpochSeconds = expiresAt,
        backendCapabilities = capabilities,
    )
}
