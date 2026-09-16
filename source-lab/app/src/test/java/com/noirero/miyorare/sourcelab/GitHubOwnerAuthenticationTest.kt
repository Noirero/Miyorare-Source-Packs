package com.noirero.miyorare.sourcelab

import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class GitHubOwnerAuthenticationTest {

    @Test
    fun `installation id is rejected before GitHub request`() {
        assertReason("GITHUB_CLIENT_ID_IS_INSTALLATION_ID") {
            GitHubOwnerAuthentication.validateClientId(SourceLabAccessPolicy.installationId.toString())
        }
    }

    @Test
    fun `app id is rejected before GitHub request`() {
        assertReason("GITHUB_CLIENT_ID_IS_APP_ID") {
            GitHubOwnerAuthentication.validateClientId(SourceLabAccessPolicy.githubAppId.toString())
        }
    }

    @Test
    fun `other numeric value is rejected`() {
        assertReason("GITHUB_CLIENT_ID_MUST_NOT_BE_NUMERIC") {
            GitHubOwnerAuthentication.validateClientId("123456789012")
        }
    }

    @Test
    fun `documented dotted GitHub App client id is accepted`() {
        GitHubOwnerAuthentication.validateClientId("Iv1.ab1112223334445c")
    }

    @Test
    fun `embedded client id wins over stale installation id recovery value`() {
        val selected = GitHubOwnerAuthentication.selectClientId(
            embeddedClientId = "Iv1.ab1112223334445c",
            recoveryClientId = SourceLabAccessPolicy.installationId.toString(),
        )
        assertEquals("Iv1.ab1112223334445c", selected)
    }

    @Test
    fun `valid recovery client id is used when embedded client id is absent`() {
        val selected = GitHubOwnerAuthentication.selectClientId(
            embeddedClientId = "",
            recoveryClientId = "Iv1.ab1112223334445c",
        )
        assertEquals("Iv1.ab1112223334445c", selected)
    }

    @Test
    fun `stale numeric recovery client id is cleared`() {
        assertEquals(
            "",
            GitHubOwnerAuthentication.normalizeRecoveryClientId(
                SourceLabAccessPolicy.installationId.toString(),
            ),
        )
        assertEquals("", GitHubOwnerAuthentication.normalizeRecoveryClientId("123456789012"))
    }

    private fun assertReason(expected: String, block: () -> Unit) {
        try {
            block()
            fail("Expected GitHubOwnerAuthenticationException")
        } catch (error: GitHubOwnerAuthenticationException) {
            assertEquals(expected, error.reason)
        }
    }
}
