package com.noirero.miyorare.sourcelab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class SourceLabControlClientTest {
    private val evidence = LiveEvidenceBinding(
        farmEvidenceSha256 = "a".repeat(64),
        gateSha256 = "b".repeat(64),
        repairEvidenceSha256 = "c".repeat(64),
        repairEvidenceCount = 2,
    )

    @Test
    fun freshCycleWithLiveRecoveryCandidateAllowsRunFarm() {
        val actions = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(automation = automationCandidate("uma", "3".repeat(40), "4".repeat(40))),
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
    fun noLiveRecoveryCandidateFailsClosed() {
        val actions = SourceLabControlClient.buildAvailability(
            session = sessionWithAllCapabilities(),
            snapshot = snapshot(),
            approvalRunId = null,
            signingRunId = null,
            publishRunId = null,
        )
        assertFalse(actions.getValue(SourceLabControlAction.RUN_FARM).available)
        assertEquals("NO_RECOVERY_CANDIDATE", actions.getValue(SourceLabControlAction.RUN_FARM).reason)
    }

    @Test
    fun farmRecoveryTargetsUseOnlyExactChangedProviderCandidates() {
        val snapshot = snapshot(
            automation = LiveAutomationState(
                state = "IDLE",
                reason = "TEST",
                ownerActionRequired = false,
                workflowRunId = null,
                candidates = mapOf(
                    "uma" to LiveAutomationCandidate("1".repeat(40), "2".repeat(40)),
                    "keiyoushi" to LiveAutomationCandidate("3".repeat(40), "4".repeat(40)),
                    "gekkoushi" to LiveAutomationCandidate("5".repeat(40), "5".repeat(40)),
                    "unknown" to LiveAutomationCandidate("6".repeat(40), "7".repeat(40)),
                ),
            ),
        )

        val targets = SourceLabControlClient.farmRecoveryTargets(snapshot)
        assertEquals(listOf("keiyoushi", "uma"), targets.map { it.provider })
        assertEquals("4".repeat(40), targets[0].candidate)
        assertEquals("2".repeat(40), targets[1].candidate)
    }

    @Test
    fun nonKeiyoushiRecoveryDispatchMatchesBackendInputsAndRunTitle() {
        val candidate = "4".repeat(40)
        val snapshot = snapshot(automation = automationCandidate("uma", "3".repeat(40), candidate))
        val spec = SourceLabControlClient.buildFarmRecoveryDispatchSpec(
            snapshot = snapshot,
            request = SourceLabFarmRecoveryRequest(provider = "uma", expectedCandidate = candidate),
            requestId = "a".repeat(32),
        )

        assertEquals("source-lab-run-farm.yml", spec.workflow)
        assertEquals("Source Lab run farm ${"a".repeat(32)} (uma)", spec.title)
        assertEquals(
            mapOf(
                "request_id" to "a".repeat(32),
                "provider" to "uma",
                "expected_candidate" to candidate,
            ),
            spec.inputs,
        )
    }

    @Test
    fun keiyoushiRecoveryRequiresAndBindsExactRuntimeEvidenceRun() {
        val candidate = "4".repeat(40)
        val snapshot = snapshot(automation = automationCandidate("keiyoushi", "3".repeat(40), candidate))

        assertControlReason("RUNTIME_EVIDENCE_RUN_ID_REQUIRED") {
            SourceLabControlClient.buildFarmRecoveryDispatchSpec(
                snapshot = snapshot,
                request = SourceLabFarmRecoveryRequest(provider = "keiyoushi", expectedCandidate = candidate),
                requestId = "b".repeat(32),
            )
        }

        val spec = SourceLabControlClient.buildFarmRecoveryDispatchSpec(
            snapshot = snapshot,
            request = SourceLabFarmRecoveryRequest(
                provider = "keiyoushi",
                expectedCandidate = candidate,
                runtimeEvidenceRunId = 39020361429L,
            ),
            requestId = "b".repeat(32),
        )
        assertEquals("39020361429", spec.inputs["runtime_evidence_run_id"])
        assertEquals(candidate, spec.inputs["expected_candidate"])
        assertEquals("keiyoushi", spec.inputs["provider"])
    }

    @Test
    fun changedCandidateIsRejectedBeforeDispatch() {
        val snapshot = snapshot(
            automation = automationCandidate("uma", "3".repeat(40), "5".repeat(40)),
        )
        assertControlReason("EXPECTED_CANDIDATE_CHANGED") {
            SourceLabControlClient.buildFarmRecoveryDispatchSpec(
                snapshot = snapshot,
                request = SourceLabFarmRecoveryRequest(
                    provider = "uma",
                    expectedCandidate = "4".repeat(40),
                ),
                requestId = "c".repeat(32),
            )
        }
    }

    @Test
    fun runtimeEvidenceCannotBeAttachedToAnotherProvider() {
        val candidate = "4".repeat(40)
        val snapshot = snapshot(automation = automationCandidate("uma", "3".repeat(40), candidate))
        assertControlReason("RUNTIME_EVIDENCE_NOT_APPLICABLE") {
            SourceLabControlClient.buildFarmRecoveryDispatchSpec(
                snapshot = snapshot,
                request = SourceLabFarmRecoveryRequest(
                    provider = "uma",
                    expectedCandidate = candidate,
                    runtimeEvidenceRunId = 99L,
                ),
                requestId = "d".repeat(32),
            )
        }
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
    fun publishedCycleAllowsNextFarmOnlyWhenNewCandidateExists() {
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
            snapshot = snapshot(
                promotion = promotion,
                published = published,
                automation = automationCandidate("uma", "4".repeat(40), "5".repeat(40)),
            ),
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

    private fun assertControlReason(expected: String, block: () -> Unit) {
        try {
            block()
            fail("Expected SourceLabControlException: $expected")
        } catch (error: SourceLabControlException) {
            assertEquals(expected, error.reason)
        }
    }

    private fun automationCandidate(provider: String, current: String, candidate: String) =
        LiveAutomationState(
            state = "IDLE",
            reason = "TEST",
            ownerActionRequired = false,
            workflowRunId = null,
            candidates = mapOf(provider to LiveAutomationCandidate(current, candidate)),
        )

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
        automation: LiveAutomationState? = null,
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
        automation = automation,
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
