package com.noirero.miyorare.sourcelab

import org.json.JSONObject

internal data class FarmCoverageEvidence(
    val canonicalExecuted: Int,
    val totalRegisteredSources: Int,
    val fullyExercisedSources: Int,
    val providerMembershipsExecuted: Int,
    val totalProviderMemberships: Int,
    val missingProviderMemberships: Int,
    val failingProviderMemberships: Int,
    val fullCanonicalCoverage: Boolean,
    val fullProviderMembershipCoverage: Boolean,
)

internal data class FarmRepairEvidence(
    val reportedMemberships: Int,
    val validatedByRealParserRetest: Int,
    val failedRealParserRetest: Int,
)

internal data class AuthoritativeFarmEvidence(
    val updateState: String,
    val approvalState: String,
    val maintenanceMode: String,
    val candidateMode: Boolean,
    val candidatePass: Boolean,
    val parserExecution: Boolean,
    val executionMode: String,
    val gateReleaseState: String,
    val aggregateReleaseGate: String,
    val suiteStatus: String,
    val ownerActionRequired: Boolean,
    val publishEligible: Boolean,
    val coverage: FarmCoverageEvidence,
    val repair: FarmRepairEvidence,
) {
    val readyForApproval: Boolean
        get() =
            updateState == "CANDIDATE" &&
                approvalState == "WAITING_FOR_APPROVAL" &&
                maintenanceMode == "APPROVE_ONLY" &&
                candidateMode &&
                candidatePass &&
                parserExecution &&
                executionMode == "real-kotlin-parser-aggregate" &&
                gateReleaseState == "WAITING_FOR_APPROVAL" &&
                aggregateReleaseGate == "REAL_PARSER_READY" &&
                suiteStatus == "PASS" &&
                !ownerActionRequired &&
                !publishEligible &&
                coverage.fullCanonicalCoverage &&
                coverage.fullProviderMembershipCoverage &&
                coverage.canonicalExecuted == coverage.totalRegisteredSources &&
                coverage.fullyExercisedSources == coverage.totalRegisteredSources &&
                coverage.providerMembershipsExecuted == coverage.totalProviderMemberships &&
                coverage.missingProviderMemberships == 0 &&
                coverage.failingProviderMemberships == 0 &&
                repair.failedRealParserRetest == 0 &&
                repair.validatedByRealParserRetest == repair.reportedMemberships
}

/**
 * Parses the two authoritative JSON files emitted by the Compatibility Farm artifact.
 *
 * Workflow success alone is deliberately insufficient. The result is ready only when
 * candidate-gate.json and real-parser-harness-aggregate.json agree on full real-parser
 * coverage and the fail-closed invariants are satisfied.
 */
internal object FarmEvidenceParser {
    fun parse(candidateGateJson: String, aggregateJson: String): AuthoritativeFarmEvidence {
        val gate = JSONObject(candidateGateJson)
        val aggregate = JSONObject(aggregateJson)
        val gateEvidence = gate.requireObject("evidence")
        val gateCoverage = gateEvidence.requireObject("coverage")
        val aggregateCoverage = aggregate.requireObject("coverage")

        requireCoverageAgreement(gateCoverage, aggregateCoverage)

        val gateRepair = gateEvidence.requireObject("repairEvidence")
        val aggregateRepair = aggregate.requireObject("repairEvidence")
        requireRepairAgreement(gateRepair, aggregateRepair)

        check(gate.requireBoolean("candidateMode")) { "candidateMode must be true" }
        check(gate.requireString("maintenanceMode") == "APPROVE_ONLY") {
            "maintenanceMode must be APPROVE_ONLY"
        }
        check(gate.requireBoolean("evidence", "candidatePass")) {
            "candidate gate evidence must pass"
        }
        check(aggregate.requireBoolean("candidatePass")) {
            "aggregate candidatePass must be true"
        }

        return AuthoritativeFarmEvidence(
            updateState = gate.requireString("updateState"),
            approvalState = gate.requireString("approvalState"),
            maintenanceMode = gate.requireString("maintenanceMode"),
            candidateMode = gate.requireBoolean("candidateMode"),
            candidatePass = aggregate.requireBoolean("candidatePass"),
            parserExecution = aggregate.requireBoolean("parserExecution"),
            executionMode = aggregate.requireString("executionMode"),
            gateReleaseState = gate.requireString("releaseGate"),
            aggregateReleaseGate = aggregate.requireString("releaseGate"),
            suiteStatus = aggregate.requireString("suiteStatus"),
            ownerActionRequired = gate.requireBoolean("ownerActionRequired"),
            publishEligible = gate.requireBoolean("publishEligible"),
            coverage = gateCoverage.toCoverage(),
            repair = gateRepair.toRepair(),
        )
    }

    private fun requireCoverageAgreement(gate: JSONObject, aggregate: JSONObject) {
        val fields = listOf(
            "canonicalExecuted",
            "totalRegisteredSources",
            "fullyExercisedSources",
            "providerMembershipsExecuted",
            "totalProviderMemberships",
            "missingProviderMemberships",
            "failingProviderMemberships",
            "fullCanonicalCoverage",
            "fullProviderMembershipCoverage",
        )
        fields.forEach { field ->
            check(gate.has(field) && aggregate.has(field)) { "missing coverage field: $field" }
            check(gate.get(field).toString() == aggregate.get(field).toString()) {
                "coverage mismatch for $field"
            }
        }
    }

    private fun requireRepairAgreement(gate: JSONObject, aggregate: JSONObject) {
        val fields = listOf(
            "reportedMemberships",
            "validatedByRealParserRetest",
            "failedRealParserRetest",
        )
        fields.forEach { field ->
            check(gate.has(field) && aggregate.has(field)) { "missing repair field: $field" }
            check(gate.getInt(field) == aggregate.getInt(field)) { "repair mismatch for $field" }
        }
    }

    private fun JSONObject.toCoverage() = FarmCoverageEvidence(
        canonicalExecuted = requireInt("canonicalExecuted"),
        totalRegisteredSources = requireInt("totalRegisteredSources"),
        fullyExercisedSources = requireInt("fullyExercisedSources"),
        providerMembershipsExecuted = requireInt("providerMembershipsExecuted"),
        totalProviderMemberships = requireInt("totalProviderMemberships"),
        missingProviderMemberships = requireInt("missingProviderMemberships"),
        failingProviderMemberships = requireInt("failingProviderMemberships"),
        fullCanonicalCoverage = requireBoolean("fullCanonicalCoverage"),
        fullProviderMembershipCoverage = requireBoolean("fullProviderMembershipCoverage"),
    )

    private fun JSONObject.toRepair() = FarmRepairEvidence(
        reportedMemberships = requireInt("reportedMemberships"),
        validatedByRealParserRetest = requireInt("validatedByRealParserRetest"),
        failedRealParserRetest = requireInt("failedRealParserRetest"),
    )

    private fun JSONObject.requireObject(name: String): JSONObject {
        check(has(name) && !isNull(name)) { "missing object: $name" }
        return getJSONObject(name)
    }

    private fun JSONObject.requireString(name: String): String {
        check(has(name) && !isNull(name)) { "missing string: $name" }
        return getString(name)
    }

    private fun JSONObject.requireBoolean(name: String): Boolean {
        check(has(name) && !isNull(name)) { "missing boolean: $name" }
        return getBoolean(name)
    }

    private fun JSONObject.requireInt(name: String): Int {
        check(has(name) && !isNull(name)) { "missing int: $name" }
        return getInt(name)
    }

    private fun JSONObject.requireBoolean(parent: String, name: String): Boolean =
        requireObject(parent).requireBoolean(name)
}
