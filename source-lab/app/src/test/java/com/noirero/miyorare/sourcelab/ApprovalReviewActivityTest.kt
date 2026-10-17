package com.noirero.miyorare.sourcelab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ApprovalReviewActivityTest {
    @Test
    fun parseComparisonSummarizesDiffMetadataWithoutPatchBody() {
        val payload = """
            {
              "status": "ahead",
              "ahead_by": 3,
              "behind_by": 0,
              "total_commits": 3,
              "html_url": "https://github.com/example/repo/compare/old...new",
              "files": [
                {"filename": "a.kt", "additions": 12, "deletions": 4},
                {"filename": "b.kt", "additions": 2, "deletions": 8}
              ]
            }
        """.trimIndent()

        val summary = ProviderComparisonRepository.parseComparison(
            provider = "uma",
            repository = "example/repo",
            current = "a".repeat(40),
            candidate = "b".repeat(40),
            payload = payload,
        )

        assertEquals("ahead", summary.status)
        assertEquals(3, summary.aheadBy)
        assertEquals(0, summary.behindBy)
        assertEquals(3, summary.totalCommits)
        assertEquals(2, summary.changedFiles)
        assertEquals(14, summary.additions)
        assertEquals(12, summary.deletions)
        assertEquals("https://github.com/example/repo/compare/old...new", summary.htmlUrl)
    }

    @Test
    fun newerLiveUpstreamDoesNotReplaceLockedCandidate() {
        val expected = "1".repeat(40)
        val locked = "2".repeat(40)
        val live = "3".repeat(40)
        val authority = resolveCandidateAuthority(
            providerState = providerState(expected),
            refs = LiveCandidateProvider(current = expected, candidate = locked),
            live = LiveAutomationCandidate(current = expected, candidate = live),
        )

        assertEquals("LOCKED · UPSTREAM MOVED", authority.label)
        assertEquals(live, authority.liveCandidate)
        assertTrue(authority.baselineMatches == true)
        assertTrue(authority.automationBaselineMatches == true)
        assertFalse(authority.liveMatchesLocked == true)
    }

    @Test
    fun baselineDriftTakesPrecedenceOverLiveCandidateMatch() {
        val expected = "4".repeat(40)
        val drifted = "5".repeat(40)
        val locked = "6".repeat(40)
        val authority = resolveCandidateAuthority(
            providerState = providerState(drifted),
            refs = LiveCandidateProvider(current = expected, candidate = locked),
            live = LiveAutomationCandidate(current = expected, candidate = locked),
        )

        assertEquals("BASELINE DRIFT", authority.label)
        assertFalse(authority.baselineMatches == true)
        assertTrue(authority.liveMatchesLocked == true)
    }

    private fun providerState(commit: String) = LiveProviderState(
        id = "keiyoushi",
        updateState = "PROMOTED",
        runtimeHealth = "HEALTHY",
        activeCommit = commit,
        lastKnownGood = commit,
        recoveryState = "IDLE",
        reason = null,
        releaseEligibility = "ELIGIBLE",
        releaseEligibilityReason = "ACTIVE_COMMIT_IS_LAST_KNOWN_GOOD",
    )
}
