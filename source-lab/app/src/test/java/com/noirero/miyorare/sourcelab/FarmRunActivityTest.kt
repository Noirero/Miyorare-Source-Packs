package com.noirero.miyorare.sourcelab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FarmRunActivityTest {
    @Test
    fun compatibilityPassPercentCountsOnlyRealParserExecutionJobs() {
        val jobs = listOf(
            job(1, "candidate-farm / Candidate UMA real parser", "success"),
            job(2, "candidate-farm / Candidate Gekkoushi real parser", "success"),
            job(3, "candidate-farm / Candidate Keiyoushi mangadex", "failure"),
            job(4, "Validate Owner and repository context", "success"),
            job(5, "Cleanup isolated Farm branch", "success"),
        )

        assertEquals(66, compatibilityPassPercent(jobs))
        assertTrue(isCompatibilityExecutionJob(jobs[0]))
        assertTrue(isCompatibilityExecutionJob(jobs[2]))
        assertFalse(isCompatibilityExecutionJob(jobs[3]))
    }

    @Test
    fun compatibilityPassPercentIsUnknownWhenNoParserJobsAreVisible() {
        val jobs = listOf(job(1, "Dispatch upstream sync", "success"))
        assertNull(compatibilityPassPercent(jobs))
    }

    private fun job(id: Long, name: String, conclusion: String) = MonitoredFarmJob(
        id = id,
        name = name,
        status = "completed",
        conclusion = conclusion,
        steps = emptyList(),
    )
}
