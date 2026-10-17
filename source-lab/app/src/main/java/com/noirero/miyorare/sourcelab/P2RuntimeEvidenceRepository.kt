package com.noirero.miyorare.sourcelab

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

internal data class P2BatcaveRuntimeEvidence(
    val workflowRunId: Long,
    val workflowRunUrl: String,
    val workflowHeadSha: String,
    val workflowCreatedAt: String,
    val baseRevision: String,
    val candidateRevision: String,
    val runtimeClosureRevision: String,
    val runtimeResult: String,
    val infrastructureBlocked: Boolean,
    val requiresAndroidWebView: Boolean,
    val androidWebViewExecutionProven: Boolean,
    val miyorareRevision: String,
    val extensionPackageName: String,
    val extensionInstallSucceeded: Boolean,
    val extensionLoadSucceeded: Boolean,
    val sourceRequestSucceeded: Boolean,
    val sourceResultCount: Int,
    val dleGuardTrustCookieObserved: Boolean,
    val webViewAvailable: Boolean,
    val webViewPackageName: String,
    val webViewVersion: String,
    val probeError: String?,
)

internal object P2RuntimeEvidenceRepository {
    private const val repository = "Noirero/Miyorare-Source-Packs"
    private const val apiBase = "https://api.github.com/repos/$repository"
    private const val workflowFile = "batcave-android-webview-evidence.yml"
    private const val evidenceJobName = "Execute exact BATCAVE runtime in Miyorare Android WebView"
    private const val canonicalBatcave = "miyorare:miyorare-en:BATCAVE"
    private const val maxLogChars = 6_000_000
    private val gitCommitPattern = Regex("^[0-9a-f]{40}$")
    private val timestampPrefix = Regex("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?Z\\s?")

    suspend fun loadBatcaveEvidence(): P2BatcaveRuntimeEvidence = withContext(Dispatchers.IO) {
        val runs = JSONObject(
            fetchText("$apiBase/actions/workflows/$workflowFile/runs?status=completed&per_page=30"),
        ).getJSONArray("workflow_runs")

        for (index in 0 until runs.length()) {
            val run = runs.getJSONObject(index)
            if (run.optString("conclusion") != "success") continue
            val runId = run.optLong("id", 0L)
            if (runId <= 0L) continue

            val jobs = JSONObject(fetchText("$apiBase/actions/runs/$runId/jobs?per_page=100"))
                .getJSONArray("jobs")
            var jobId = 0L
            for (jobIndex in 0 until jobs.length()) {
                val job = jobs.getJSONObject(jobIndex)
                if (
                    job.optString("name") == evidenceJobName &&
                    job.optString("conclusion") == "success"
                ) {
                    jobId = job.optLong("id", 0L)
                    break
                }
            }
            if (jobId <= 0L) continue

            val parsed = runCatching {
                parseBatcaveJobLog(
                    logText = fetchText("$apiBase/actions/jobs/$jobId/logs", accept = "text/plain"),
                    expectedRunId = runId,
                    runHtmlUrl = run.optString("html_url"),
                    workflowHeadSha = run.optString("head_sha"),
                    workflowCreatedAt = run.optString("created_at"),
                )
            }.getOrNull()
            if (parsed != null) return@withContext parsed
        }

        error("P2_BATCAVE_EVIDENCE_UNAVAILABLE")
    }

    internal fun parseBatcaveJobLog(
        logText: String,
        expectedRunId: Long,
        runHtmlUrl: String = "",
        workflowHeadSha: String = "",
        workflowCreatedAt: String = "",
    ): P2BatcaveRuntimeEvidence {
        require(expectedRunId > 0L) { "P2 workflow run id must be positive" }
        if (workflowHeadSha.isNotBlank()) {
            require(gitCommitPattern.matches(workflowHeadSha)) { "P2 workflow head must be an exact git SHA" }
        }

        val objects = extractJsonObjects(logText)
        val probeMatches = objects.filter { candidate ->
            candidate.optInt("schema", -1) == 1 &&
                candidate.optString("canonicalId") == canonicalBatcave &&
                candidate.optString("runtime") == "miyorare-android-instrumentation" &&
                candidate.optLong("workflowRunId", -1L) == expectedRunId &&
                candidate.has("webView")
        }
        require(probeMatches.size == 1) {
            "Expected exactly one exact-run BATCAVE Android probe, got ${probeMatches.size}"
        }
        val probe = probeMatches.single()

        val reportMatches = objects.filter { candidate ->
            if (candidate.optInt("schema", -1) != 1 || !candidate.has("proofs")) return@filter false
            val proofs = candidate.optJSONArray("proofs") ?: return@filter false
            (0 until proofs.length()).any { proofIndex ->
                proofs.optJSONObject(proofIndex)?.let { proof ->
                    proof.optString("canonicalId") == canonicalBatcave &&
                        proof.optJSONObject("androidWebViewEvidence")?.optLong("workflowRunId", -1L) == expectedRunId
                } == true
            }
        }
        require(reportMatches.size == 1) {
            "Expected exactly one exact-run BATCAVE bound proof, got ${reportMatches.size}"
        }
        val report = reportMatches.single()

        val base = report.getString("base")
        val candidate = report.getString("candidate")
        require(gitCommitPattern.matches(base)) { "P2 base revision is not an exact git SHA" }
        require(gitCommitPattern.matches(candidate)) { "P2 candidate revision is not an exact git SHA" }

        val proofs = report.getJSONArray("proofs")
        val matchingProofs = buildList {
            for (index in 0 until proofs.length()) {
                val proof = proofs.optJSONObject(index) ?: continue
                if (proof.optString("canonicalId") == canonicalBatcave) add(proof)
            }
        }
        require(matchingProofs.size == 1) { "P2 bound report must contain exactly one BATCAVE proof" }
        val proof = matchingProofs.single()
        val bound = proof.getJSONObject("androidWebViewEvidence")

        val probeCandidate = probe.getString("candidateRevision")
        val miyorareRevision = probe.getString("miyorareRevision")
        require(gitCommitPattern.matches(probeCandidate)) { "P2 probe candidate is not an exact git SHA" }
        require(gitCommitPattern.matches(miyorareRevision)) { "P2 Miyorare revision is not an exact git SHA" }
        require(probe.optString("providerHost") == "batcave.biz") { "P2 BATCAVE provider host mismatch" }
        require(probeCandidate == candidate) { "P2 probe candidate does not match bound report" }
        require(proof.getString("baseRevision") == base) { "P2 proof base does not match envelope" }
        require(proof.getString("candidateRevision") == candidate) { "P2 proof candidate does not match envelope" }
        require(proof.getString("runtimeClosureRevision") == candidate) { "P2 runtime closure does not match candidate" }
        require(proof.getBoolean("requiresAndroidWebView")) { "BATCAVE P2 proof must require Android WebView" }

        require(bound.getInt("schemaVersion") == 1) { "Unsupported P2 Android WebView evidence schema" }
        require(bound.getString("runtime") == "miyorare-android-instrumentation") { "P2 runtime mismatch" }
        require(bound.getLong("workflowRunId") == expectedRunId) { "P2 bound workflow run mismatch" }
        require(bound.getString("candidateRevision") == candidate) { "P2 bound candidate mismatch" }
        require(bound.getString("miyorareRevision") == miyorareRevision) { "P2 bound Miyorare revision mismatch" }

        val extensionPackage = probe.getString("extensionPackageName")
        require(extensionPackage.isNotBlank()) { "P2 extension package is missing" }
        require(bound.getString("extensionPackageName") == extensionPackage) { "P2 extension package binding mismatch" }
        require(probe.optString("sourceName") == "BatCave") { "P2 source identity mismatch" }

        val sourceRequestSucceeded = probe.getBoolean("sourceRequestSucceeded")
        val sourceResultCount = probe.getInt("sourceResultCount")
        val trustObserved = probe.getBoolean("dleGuardTrustCookieObserved")
        require(bound.getBoolean("sourceRequestSucceeded") == sourceRequestSucceeded) { "P2 request binding mismatch" }
        require(bound.getInt("sourceResultCount") == sourceResultCount) { "P2 result-count binding mismatch" }
        require(bound.getBoolean("dleGuardTrustCookieObserved") == trustObserved) { "P2 trust-cookie binding mismatch" }

        val webView = probe.getJSONObject("webView")
        val webViewAvailable = webView.getBoolean("available")
        val webViewPackage = webView.optString("packageName")
        val webViewVersion = webView.optString("versionName")
        require(bound.optString("webViewPackageName") == webViewPackage) { "P2 WebView package binding mismatch" }
        require(bound.optString("webViewVersion") == webViewVersion) { "P2 WebView version binding mismatch" }

        val probeError = nullableString(probe, "error")
        require(nullableString(bound, "probeError") == probeError) { "P2 probe error binding mismatch" }

        val proven = proof.getBoolean("androidWebViewExecutionProven")
        val boundProven = bound.getBoolean("androidWebViewExecutionProven")
        val infrastructureBlocked = proof.getBoolean("infrastructureBlocked")
        require(proven == boundProven) { "P2 protected-path proof binding mismatch" }
        require(infrastructureBlocked == !proven) { "P2 infrastructure-blocked state is inconsistent" }

        val installSucceeded = probe.getBoolean("extensionInstallSucceeded")
        val loadSucceeded = probe.getBoolean("extensionLoadSucceeded")
        if (proven) {
            require(
                proof.getString("result") == "PASS" &&
                    installSucceeded &&
                    loadSucceeded &&
                    sourceRequestSucceeded &&
                    sourceResultCount > 0 &&
                    trustObserved &&
                    webViewAvailable &&
                    webViewPackage.isNotBlank() &&
                    webViewVersion.isNotBlank(),
            ) { "P2 positive protected-path proof lacks required runtime evidence" }
        }

        return P2BatcaveRuntimeEvidence(
            workflowRunId = expectedRunId,
            workflowRunUrl = runHtmlUrl,
            workflowHeadSha = workflowHeadSha,
            workflowCreatedAt = workflowCreatedAt,
            baseRevision = base,
            candidateRevision = candidate,
            runtimeClosureRevision = proof.getString("runtimeClosureRevision"),
            runtimeResult = proof.getString("result"),
            infrastructureBlocked = infrastructureBlocked,
            requiresAndroidWebView = true,
            androidWebViewExecutionProven = proven,
            miyorareRevision = miyorareRevision,
            extensionPackageName = extensionPackage,
            extensionInstallSucceeded = installSucceeded,
            extensionLoadSucceeded = loadSucceeded,
            sourceRequestSucceeded = sourceRequestSucceeded,
            sourceResultCount = sourceResultCount,
            dleGuardTrustCookieObserved = trustObserved,
            webViewAvailable = webViewAvailable,
            webViewPackageName = webViewPackage,
            webViewVersion = webViewVersion,
            probeError = probeError,
        )
    }

    private fun extractJsonObjects(logText: String): List<JSONObject> {
        val result = mutableListOf<JSONObject>()
        var builder: StringBuilder? = null

        logText.lineSequence().forEach { rawLine ->
            val line = timestampPrefix.replace(rawLine, "")
            val trimmed = line.trim()
            if (builder == null) {
                if (trimmed != "{" && !(trimmed.startsWith("{") && trimmed.endsWith("}"))) {
                    return@forEach
                }
                builder = StringBuilder(trimmed)
            } else {
                builder?.append('\n')?.append(line)
            }

            val current = builder ?: return@forEach
            if (!trimmed.endsWith("}")) return@forEach
            val parsed = runCatching { JSONObject(current.toString()) }.getOrNull() ?: return@forEach
            result += parsed
            builder = null
        }
        return result
    }

    private fun nullableString(json: JSONObject, key: String): String? =
        if (!json.has(key) || json.isNull(key)) null else json.getString(key)

    private fun fetchText(url: String, accept: String = "application/vnd.github+json"): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10_000
            readTimeout = 30_000
            instanceFollowRedirects = true
            setRequestProperty("Accept", accept)
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/${BuildConfig.VERSION_NAME}")
            useCaches = false
        }
        return try {
            val statusCode = connection.responseCode
            if (statusCode !in 200..299) {
                error("HTTP $statusCode while reading P2 runtime evidence")
            }
            val text = connection.inputStream.bufferedReader().use { reader ->
                val output = StringBuilder()
                val buffer = CharArray(8_192)
                while (true) {
                    val count = reader.read(buffer)
                    if (count < 0) break
                    if (output.length + count > maxLogChars) {
                        error("P2 runtime evidence log exceeds safe read limit")
                    }
                    output.append(buffer, 0, count)
                }
                output.toString()
            }
            text
        } finally {
            connection.disconnect()
        }
    }
}
