package com.noirero.miyorare.sourcelab

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SourceLabControlClientTest {
    private val evidence = LiveEvidenceBinding(
        farmEvidenceSha256 = "a".repeat(64),
        gateSha256 = "b".repeat(64),
        repairEvidenceSha256 = "c".repeat(64),
        repairEvidenceCount = 2,
    )

    @Test
    fun freshCycleOnlyAllowsRunFarm() {
        val actions = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(),
            approvalRunId = null,
            signingRunId = null,
            publishRunId = null,
        )
        assertTrue(actions.getValue(SourceLabControlAction.RUN_FARM).available)
        assertFalse(actions.getValue(SourceLabControlAction.APPROVE).available)
        assertFalse(actions.getValue(SourceLabControlAction.PROMOTE).available)
        assertFalse(actions.getValue(SourceLabControlAction.SIGN).available)
        assertFalse(actions.getValue(SourceLabControlAction.PUBLISH).available)
    }

    @Test
    fun readyPendingSourcesExposeOneClickApproval() {
        val actions = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(
                pendingWorker = LivePendingWorkerState(
                    schemaVersion = 2,
                    readyCount = 3,
                    retryCount = 2,
                    needsAttentionCount = 1,
                    approvedCount = 4,
                    readyCanonicalIds = listOf("a", "b", "c"),
                    updatedAt = "2026-09-18T02:00:00Z",
                ),
            ),
            approvalRunId = null,
            signingRunId = null,
            publishRunId = null,
        )
        assertTrue(actions.getValue(SourceLabControlAction.APPROVE_READY_SOURCES).available)
    }

    @Test
    fun noReadySourceOrMissingWorkerStateFailsClosed() {
        val noWorker = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(),
            approvalRunId = null,
            signingRunId = null,
            publishRunId = null,
        )
        assertFalse(noWorker.getValue(SourceLabControlAction.APPROVE_READY_SOURCES).available)

        val emptyWorker = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(
                pendingWorker = LivePendingWorkerState(
                    schemaVersion = 2,
                    readyCount = 0,
                    retryCount = 3,
                    needsAttentionCount = 0,
                    approvedCount = 0,
                    readyCanonicalIds = emptyList(),
                    updatedAt = null,
                ),
            ),
            approvalRunId = null,
            signingRunId = null,
            publishRunId = null,
        )
        assertFalse(emptyWorker.getValue(SourceLabControlAction.APPROVE_READY_SOURCES).available)
    }

    @Test
    fun providerApprovalPipelineLocksSourceOnboardingApproval() {
        val actions = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(
                candidate = candidate(),
                pendingWorker = LivePendingWorkerState(
                    schemaVersion = 2,
                    readyCount = 2,
                    retryCount = 0,
                    needsAttentionCount = 0,
                    approvedCount = 0,
                    readyCanonicalIds = listOf("a", "b"),
                    updatedAt = null,
                ),
            ),
            approvalRunId = null,
            signingRunId = null,
            publishRunId = null,
        )
        assertFalse(actions.getValue(SourceLabControlAction.APPROVE_READY_SOURCES).available)
    }

    @Test
    fun stagedCandidateAllowsApproveButNotPromoteWithoutReceipt() {
        val actions = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(candidate = candidate()),
            approvalRunId = null,
            signingRunId = null,
            publishRunId = null,
        )
        assertFalse(actions.getValue(SourceLabControlAction.RUN_FARM).available)
        assertTrue(actions.getValue(SourceLabControlAction.APPROVE).available)
        assertFalse(actions.getValue(SourceLabControlAction.PROMOTE).available)
    }

    @Test
    fun approvalReceiptMovesControlToPromote() {
        val actions = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(candidate = candidate()),
            approvalRunId = 101L,
            signingRunId = null,
            publishRunId = null,
        )
        assertFalse(actions.getValue(SourceLabControlAction.APPROVE).available)
        assertTrue(actions.getValue(SourceLabControlAction.PROMOTE).available)
    }

    @Test
    fun promotedCandidateRequiresSignBeforePublish() {
        val actions = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(promotion = promotion()),
            approvalRunId = null,
            signingRunId = null,
            publishRunId = null,
        )
        assertFalse(actions.getValue(SourceLabControlAction.RUN_FARM).available)
        assertTrue(actions.getValue(SourceLabControlAction.SIGN).available)
        assertFalse(actions.getValue(SourceLabControlAction.PUBLISH).available)
    }

    @Test
    fun signedCandidateAllowsPublish() {
        val actions = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(promotion = promotion()),
            approvalRunId = null,
            signingRunId = 202L,
            publishRunId = null,
        )
        assertFalse(actions.getValue(SourceLabControlAction.SIGN).available)
        assertTrue(actions.getValue(SourceLabControlAction.PUBLISH).available)
    }

    @Test
    fun publishedCycleAllowsNextFarmAndBlocksReplay() {
        val promotion = promotion()
        val published = LivePublishState(
            candidateSetId = promotion.candidateSetId,
            signingRunId = 202L,
            publishRunId = 303L,
            releaseRunId = 404L,
            foundationCommit = "d".repeat(40),
            providers = promotion.providers,
            version = "0.5.1",
            tag = "miyorare-sources-v0.5.1",
        )
        val actions = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(promotion = promotion, published = published),
            approvalRunId = null,
            signingRunId = 202L,
            publishRunId = 303L,
        )
        assertTrue(actions.getValue(SourceLabControlAction.RUN_FARM).available)
        assertFalse(actions.getValue(SourceLabControlAction.SIGN).available)
        assertFalse(actions.getValue(SourceLabControlAction.PUBLISH).available)
    }

    @Test
    fun missingBackendCapabilityAlwaysFailsClosed() {
        val session = sessionWithAllCapabilities().copy(
            backendCapabilities = setOf(SourceLabControlAction.RUN_FARM),
        )
        val actions = SourceLabControlClient.buildAvailability(
            session = session,
            snapshot = snapshot(candidate = candidate()),
            approvalRunId = null,
            signingRunId = null,
            publishRunId = null,
        )
        assertFalse(actions.getValue(SourceLabControlAction.APPROVE).available)
        assertFalse(actions.getValue(SourceLabControlAction.PROMOTE).available)
        assertFalse(actions.getValue(SourceLabControlAction.SIGN).available)
        assertFalse(actions.getValue(SourceLabControlAction.PUBLISH).available)
    }

    private fun candidate() = LiveApprovalCandidate(
        candidateSetId = "1".repeat(64),
        state = "WAITING_FOR_APPROVAL",
        gateFingerprint = "2".repeat(64),
        providers = mapOf(
            "uma" to LiveCandidateProvider("3".repeat(40), "4".repeat(40)),
        ),
        evidenceBinding = evidence,
        publishEligible = false,
    )

    private fun promotion() = LivePromotionState(
        candidateSetId = "1".repeat(64),
        promotionRunId = 111L,
        providers = mapOf("uma" to "4".repeat(40)),
        evidenceBinding = evidence,
        publishEligible = false,
    )

    private fun snapshot(
        candidate: LiveApprovalCandidate? = null,
        promotion: LivePromotionState? = null,
        published: LivePublishState? = null,
        pendingWorker: LivePendingWorkerState? = null,
    ) = LiveFarmSnapshot(
        sources = emptyList(),
        providers = emptyList(),
        recentRuns = emptyList(),
        approvalCandidate = candidate,
        lastPromotion = promotion,
        lastPublish = published,
        cohort = "seed-12",
        targetSize = 12,
        branch = SourceLabRepository.farmBranch,
        retrievedAtEpochMs = 0L,
        pendingWorker = pendingWorker,
    )

    private fun sessionWithAllCapabilities() = OwnerAccessSession(
        authenticated = true,
        githubUserId = SourceLabAccessPolicy.ownerGithubUserId,
        githubAppId = SourceLabAccessPolicy.githubAppId,
        installationId = SourceLabAccessPolicy.installationId,
        repository = SourceLabAccessPolicy.repository,
        repositoryPermission = "admin",
        backendAuthorized = true,
        backendAuthorizationExpiresAtEpochSeconds = System.currentTimeMillis() / 1000L + 300L,
        backendCapabilities = SourceLabControlAction.entries.toSet(),
    )
}
