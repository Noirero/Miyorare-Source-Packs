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

    private fun assertReason(expected: String, block: () -> Unit) {
        try {
            block()
            fail("Expected GitHubOwnerAuthenticationException")
        } catch (error: GitHubOwnerAuthenticationException) {
            assertEquals(expected, error.reason)
        }
    }
}
