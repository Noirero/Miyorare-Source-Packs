package com.noirero.miyorare.sourcelab

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FarmEvidenceParserTest {
    @Test
    fun authoritativeSeedEvidenceIsReadyForApproval() {
        val evidence = FarmEvidenceParser.parse(validGate(), validAggregate())
        assertTrue(evidence.readyForApproval)
    }

    @Test
    fun parserExecutionFalseCannotBeReady() {
        val aggregate = validAggregate().replace("\"parserExecution\":true", "\"parserExecution\":false")
        val evidence = FarmEvidenceParser.parse(validGate(), aggregate)
        assertFalse(evidence.readyForApproval)
    }

    @Test(expected = IllegalStateException::class)
    fun mismatchedCoverageFailsClosed() {
        val aggregate = validAggregate().replace("\"providerMembershipsExecuted\":21", "\"providerMembershipsExecuted\":20")
        FarmEvidenceParser.parse(validGate(), aggregate)
    }

    @Test
    fun failedRepairRetestCannotBeReady() {
        val gate = validGate()
            .replace("\"failedRealParserRetest\":0", "\"failedRealParserRetest\":1")
            .replace("\"validatedByRealParserRetest\":2", "\"validatedByRealParserRetest\":1")
        val aggregate = validAggregate()
            .replace("\"failedRealParserRetest\":0", "\"failedRealParserRetest\":1")
            .replace("\"validatedByRealParserRetest\":2", "\"validatedByRealParserRetest\":1")
        val evidence = FarmEvidenceParser.parse(gate, aggregate)
        assertFalse(evidence.readyForApproval)
    }

    @Test(expected = IllegalStateException::class)
    fun candidateGateFailureFailsClosed() {
        val gate = validGate().replace("\"candidatePass\":true", "\"candidatePass\":false")
        FarmEvidenceParser.parse(gate, validAggregate())
    }

    private fun validGate() = """
        {
          "approvalState":"WAITING_FOR_APPROVAL",
          "candidateMode":true,
          "evidence":{
            "candidatePass":true,
            "coverage":{
              "canonicalExecuted":12,
              "failingProviderMemberships":0,
              "fullCanonicalCoverage":true,
              "fullProviderMembershipCoverage":true,
              "fullyExercisedSources":12,
              "missingProviderMemberships":0,
              "providerMembershipsExecuted":21,
              "totalProviderMemberships":21,
              "totalRegisteredSources":12
            },
            "executionMode":"real-kotlin-parser-aggregate",
            "repairEvidence":{
              "failedRealParserRetest":0,
              "reportedMemberships":2,
              "validatedByRealParserRetest":2
            },
            "sourceReleaseGate":"REAL_PARSER_READY"
          },
          "maintenanceMode":"APPROVE_ONLY",
          "nextAction":"WAIT_FOR_APPROVAL",
          "ownerActionRequired":false,
          "publishEligible":false,
          "releaseGate":"WAITING_FOR_APPROVAL",
          "updateState":"CANDIDATE"
        }
    """.trimIndent()

    private fun validAggregate() = """
        {
          "candidatePass":true,
          "coverage":{
            "canonicalExecuted":12,
            "failingProviderMemberships":0,
            "fullCanonicalCoverage":true,
            "fullProviderMembershipCoverage":true,
            "fullyExercisedSources":12,
            "missingProviderMemberships":0,
            "providerMembershipsExecuted":21,
            "totalProviderMemberships":21,
            "totalRegisteredSources":12
          },
          "executionMode":"real-kotlin-parser-aggregate",
          "ownerActionRequired":false,
          "parserExecution":true,
          "publishEligible":false,
          "releaseGate":"REAL_PARSER_READY",
          "repairEvidence":{
            "failedRealParserRetest":0,
            "reportedMemberships":2,
            "validatedByRealParserRetest":2
          },
          "schemaVersion":1,
          "suiteStatus":"PASS"
        }
    """.trimIndent()
}
