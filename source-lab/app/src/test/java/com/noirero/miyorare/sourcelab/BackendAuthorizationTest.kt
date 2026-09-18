package com.noirero.miyorare.sourcelab

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BackendAuthorizationTest {
    private val now = 1_800_000_000L
    private val challenge = "ab".repeat(32)
    private val runId = 123456789L

    @Test
    fun authorizedProofAppliesValidatedCapabilitiesWithoutSecondDownload() {
        val capabilities = setOf(
            SourceLabControlAction.RUN_FARM,
            SourceLabControlAction.APPROVE,
        )
        val session = OwnerAccessSession(
            authenticated = true,
            githubUserId = SourceLabAccessPolicy.ownerGithubUserId,
            githubAppId = SourceLabAccessPolicy.githubAppId,
            installationId = SourceLabAccessPolicy.installationId,
            repository = SourceLabAccessPolicy.repository,
            repositoryPermission = SourceLabAccessPolicy.minimumRepositoryPermission,
            backendAuthorized = false,
        )
        val applied = BackendAuthorizationProof(
            authorized = true,
            reason = "BACKEND_AUTHORIZED",
            challenge = challenge,
            runId = runId,
            expiresAtEpochSeconds = now + 300L,
            backendCapabilities = capabilities,
        ).applyTo(session)

        assertTrue(applied.backendAuthorized)
        assertEquals(capabilities, applied.backendCapabilities)
    }

    @Test
    fun exactGithubOidcClaimsAreAccepted() {
        assertNull(
            SourceLabOidcClaimsValidator.validate(
                payload = validClaims(),
                expectedChallenge = challenge,
                expectedRunId = runId,
                nowEpochSeconds = now,
            )
        )
    }

    @Test
    fun legacyGithubOidcSubjectIsAlsoAccepted() {
        val claims = validClaims().put(
            "sub",
            "repo:Noirero/Miyorare-Source-Packs:ref:refs/heads/main",
        )
        assertNull(SourceLabOidcClaimsValidator.validate(claims, challenge, runId, now))
    }

    @Test
    fun differentSubjectFailsClosed() {
        val claims = validClaims().put(
            "sub",
            "repo:someone/else:ref:refs/heads/main",
        )
        assertEquals(
            "BACKEND_CLAIM_SUBJECT_MISMATCH",
            SourceLabOidcClaimsValidator.validate(claims, challenge, runId, now),
        )
    }

    @Test
    fun differentActorFailsClosed() {
        val claims = validClaims().put("actor_id", "42")
        assertEquals(
            "BACKEND_CLAIM_ACTOR_ID_MISMATCH",
            SourceLabOidcClaimsValidator.validate(claims, challenge, runId, now),
        )
    }

    @Test
    fun differentAudienceFailsClosed() {
        val claims = validClaims().put("aud", "miyorare-source-lab:${"cd".repeat(32)}")
        assertEquals(
            "BACKEND_CLAIM_AUDIENCE_MISMATCH",
            SourceLabOidcClaimsValidator.validate(claims, challenge, runId, now),
        )
    }

    @Test
    fun differentWorkflowFailsClosed() {
        val claims = validClaims().put(
            "workflow_ref",
            "Noirero/Miyorare-Source-Packs/.github/workflows/other.yml@refs/heads/main",
        )
        assertEquals(
            "BACKEND_CLAIM_WORKFLOW_REF_MISMATCH",
            SourceLabOidcClaimsValidator.validate(claims, challenge, runId, now),
        )
    }

    @Test
    fun staleJwtFailsClosed() {
        val claims = validClaims()
            .put("iat", now - 700L)
            .put("exp", now - 100L)
        assertEquals(
            "BACKEND_CLAIM_EXPIRED",
            SourceLabOidcClaimsValidator.validate(claims, challenge, runId, now),
        )
    }

    @Test
    fun differentRunIdFailsClosed() {
        val claims = validClaims().put("run_id", "999")
        assertEquals(
            "BACKEND_CLAIM_RUN_ID_MISMATCH",
            SourceLabOidcClaimsValidator.validate(claims, challenge, runId, now),
        )
    }

    private fun validClaims() = JSONObject()
        .put("iss", "https://token.actions.githubusercontent.com")
        .put("aud", "miyorare-source-lab:$challenge")
        .put(
            "sub",
            "repo:Noirero@149634319/Miyorare-Source-Packs@1367256631:ref:refs/heads/main",
        )
        .put("repository", "Noirero/Miyorare-Source-Packs")
        .put("repository_id", SourceLabAccessPolicy.repositoryId.toString())
        .put("repository_owner_id", SourceLabAccessPolicy.ownerGithubUserId.toString())
        .put("actor_id", SourceLabAccessPolicy.ownerGithubUserId.toString())
        .put("event_name", "workflow_dispatch")
        .put("ref", "refs/heads/main")
        .put(
            "workflow_ref",
            "Noirero/Miyorare-Source-Packs/.github/workflows/source-lab-backend-authorization.yml@refs/heads/main",
        )
        .put("workflow", "Source Lab Backend Authorization")
        .put("run_id", runId.toString())
        .put("iat", now - 10L)
        .put("nbf", now - 10L)
        .put("exp", now + 300L)
}
