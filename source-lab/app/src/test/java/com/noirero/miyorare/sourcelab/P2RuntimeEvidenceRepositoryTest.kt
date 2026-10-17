package com.noirero.miyorare.sourcelab

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class P2RuntimeEvidenceRepositoryTest {
    private val base = "1".repeat(40)
    private val candidate = "2".repeat(40)
    private val miyorare = "3".repeat(40)
    private val runId = 39030425918L

    @Test
    fun currentLikeEvidenceKeepsWebViewAvailabilitySeparateFromProtectedPathProof() {
        val evidence = P2RuntimeEvidenceRepository.parseBatcaveJobLog(
            logText = buildLog(proven = false, trustObserved = false),
            expectedRunId = runId,
            runHtmlUrl = "https://github.com/Noirero/Miyorare-Source-Packs/actions/runs/$runId",
            workflowHeadSha = "4".repeat(40),
            workflowCreatedAt = "2026-10-17T12:00:00Z",
        )

        assertEquals("PASS", evidence.runtimeResult)
        assertTrue(evidence.extensionInstallSucceeded)
        assertTrue(evidence.extensionLoadSucceeded)
        assertTrue(evidence.sourceRequestSucceeded)
        assertEquals(10, evidence.sourceResultCount)
        assertTrue(evidence.webViewAvailable)
        assertEquals("com.google.android.webview", evidence.webViewPackageName)
        assertEquals("124.0.6367.219", evidence.webViewVersion)
        assertFalse(evidence.dleGuardTrustCookieObserved)
        assertFalse(evidence.androidWebViewExecutionProven)
        assertTrue(evidence.infrastructureBlocked)
        assertNull(evidence.probeError)
    }

    @Test
    fun positiveProtectedPathProofRequiresObservedTrustEvidence() {
        val evidence = P2RuntimeEvidenceRepository.parseBatcaveJobLog(
            logText = buildLog(proven = true, trustObserved = true),
            expectedRunId = runId,
        )

        assertTrue(evidence.dleGuardTrustCookieObserved)
        assertTrue(evidence.androidWebViewExecutionProven)
        assertFalse(evidence.infrastructureBlocked)
    }

    @Test(expected = IllegalArgumentException::class)
    fun boundCandidateMismatchFailsClosed() {
        P2RuntimeEvidenceRepository.parseBatcaveJobLog(
            logText = buildLog(
                proven = false,
                trustObserved = false,
                boundCandidate = "9".repeat(40),
            ),
            expectedRunId = runId,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun workflowRunMismatchFailsClosed() {
        P2RuntimeEvidenceRepository.parseBatcaveJobLog(
            logText = buildLog(proven = false, trustObserved = false),
            expectedRunId = runId + 1,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun fabricatedPositiveWithoutTrustCookieFailsClosed() {
        P2RuntimeEvidenceRepository.parseBatcaveJobLog(
            logText = buildLog(proven = true, trustObserved = false),
            expectedRunId = runId,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun unsupportedBoundEvidenceSchemaFailsClosed() {
        P2RuntimeEvidenceRepository.parseBatcaveJobLog(
            logText = buildLog(
                proven = false,
                trustObserved = false,
                boundSchemaVersion = 2,
            ),
            expectedRunId = runId,
        )
    }

    private fun buildLog(
        proven: Boolean,
        trustObserved: Boolean,
        boundCandidate: String = candidate,
        boundSchemaVersion: Int = 1,
    ): String {
        val probe = JSONObject()
            .put("schema", 1)
            .put("canonicalId", "miyorare:miyorare-en:BATCAVE")
            .put("candidateRevision", candidate)
            .put("miyorareRevision", miyorare)
            .put("workflowRunId", runId)
            .put("runtime", "miyorare-android-instrumentation")
            .put("providerHost", "batcave.biz")
            .put("extensionPackageName", "eu.kanade.tachiyomi.extension.en.batcave")
            .put("extensionInstallSucceeded", true)
            .put("extensionLoadSucceeded", true)
            .put("sourceName", "BatCave")
            .put("sourceRequestSucceeded", true)
            .put("sourceResultCount", 10)
            .put("dleGuardTrustCookieObserved", trustObserved)
            .put(
                "webView",
                JSONObject()
                    .put("available", true)
                    .put("packageName", "com.google.android.webview")
                    .put("versionName", "124.0.6367.219")
                    .put("versionCode", 636771938L),
            )
            .put("error", JSONObject.NULL)

        val boundEvidence = JSONObject()
            .put("schemaVersion", boundSchemaVersion)
            .put("runtime", "miyorare-android-instrumentation")
            .put("miyorareRevision", miyorare)
            .put("candidateRevision", boundCandidate)
            .put("workflowRunId", runId)
            .put("extensionPackageName", "eu.kanade.tachiyomi.extension.en.batcave")
            .put("sourceRequestSucceeded", true)
            .put("sourceResultCount", 10)
            .put("dleGuardTrustCookieObserved", trustObserved)
            .put("webViewPackageName", "com.google.android.webview")
            .put("webViewVersion", "124.0.6367.219")
            .put("probeError", JSONObject.NULL)
            .put("androidWebViewExecutionProven", proven)

        val proof = JSONObject()
            .put("canonicalId", "miyorare:miyorare-en:BATCAVE")
            .put("result", "PASS")
            .put("infrastructureBlocked", !proven)
            .put("baseRevision", base)
            .put("candidateRevision", candidate)
            .put("runtimeClosureRevision", candidate)
            .put("evidenceId", "github-run:$runId:miyorare:miyorare-en:BATCAVE")
            .put("requiresAndroidWebView", true)
            .put("androidWebViewExecutionProven", proven)
            .put("androidWebViewEvidence", boundEvidence)

        val report = JSONObject()
            .put("schema", 1)
            .put("base", base)
            .put("candidate", candidate)
            .put("proofs", JSONArray().put(proof))

        return buildString {
            appendLine("2026-10-17T12:00:00.0000000Z unrelated setup output")
            appendTimestampedJson(probe)
            appendLine("2026-10-17T12:00:01.0000000Z binder output follows")
            appendTimestampedJson(report)
            appendLine("2026-10-17T12:00:02.0000000Z upload complete")
        }
    }

    private fun StringBuilder.appendTimestampedJson(json: JSONObject) {
        json.toString(2).lineSequence().forEach { line ->
            append("2026-10-17T12:00:00.1234567Z ")
            appendLine(line)
        }
    }
}
