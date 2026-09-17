package com.noirero.miyorare.sourcelab

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
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
        assertTrue(GitHubOwnerAuthentication.isValidClientId("Iv1.ab1112223334445c"))
    }

    @Test
    fun `blank and numeric identifiers are never valid client ids`() {
        assertFalse(GitHubOwnerAuthentication.isValidClientId(""))
        assertFalse(GitHubOwnerAuthentication.isValidClientId(SourceLabAccessPolicy.installationId.toString()))
        assertFalse(GitHubOwnerAuthentication.isValidClientId(SourceLabAccessPolicy.githubAppId.toString()))
    }

    @Test
    fun `expiring device token response keeps refresh token metadata`() {
        val now = 1_800_000_000L
        val credential = GitHubOwnerAuthentication.parseTokenCredentialResponse(
            JSONObject()
                .put("access_token", "ghu_test_access")
                .put("expires_in", 28_800L)
                .put("refresh_token", "ghr_test_refresh")
                .put("refresh_token_expires_in", 15_897_600L),
            nowEpochSeconds = now,
        )

        assertEquals("ghu_test_access", credential.accessToken)
        assertEquals(now + 28_800L, credential.accessTokenExpiresAtEpochSeconds)
        assertEquals("ghr_test_refresh", credential.refreshToken)
        assertEquals(now + 15_897_600L, credential.refreshTokenExpiresAtEpochSeconds)
        assertFalse(GitHubOwnerAuthentication.credentialNeedsRefresh(credential, now))
        assertTrue(GitHubOwnerAuthentication.credentialNeedsRefresh(credential, now + 28_700L))
    }

    @Test
    fun `non expiring token remains valid without refresh metadata`() {
        val credential = GitHubOwnerAuthentication.parseTokenCredentialResponse(
            JSONObject().put("access_token", "ghu_non_expiring"),
            nowEpochSeconds = 1_800_000_000L,
        )

        assertNull(credential.accessTokenExpiresAtEpochSeconds)
        assertNull(credential.refreshToken)
        assertNull(credential.refreshTokenExpiresAtEpochSeconds)
        assertFalse(GitHubOwnerAuthentication.credentialNeedsRefresh(credential, 2_000_000_000L))
    }

    private fun assertReason(expected: String, block: () -> Unit) {
        try {
            block()
            fail("Expected GitHubOwnerAuthenticationException")
        } catch (error: GitHubOwnerAuthenticationException) {
            if (error.reason != expected) {
                fail("Expected $expected but got ${error.reason}")
            }
        }
    }
}
