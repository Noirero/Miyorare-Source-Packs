package com.noirero.miyorare.sourcelab

import org.junit.Assert.assertEquals
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
}
