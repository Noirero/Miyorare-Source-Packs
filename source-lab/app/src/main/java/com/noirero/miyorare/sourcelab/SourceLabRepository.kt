package com.noirero.miyorare.sourcelab

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

internal data class LiveProviderState(
    val id: String,
    val updateState: String,
    val runtimeHealth: String,
    val activeCommit: String,
    val lastKnownGood: String,
    val recoveryState: String,
    val reason: String?,
)

internal data class LiveSourceState(
    val canonicalId: String,
    val displayName: String,
    val language: String,
    val contentProfile: String,
    val authType: String,
    val adapterFamily: String,
    val providers: List<String>,
    val updateState: String,
    val runtimeHealth: String,
    val approvalState: String,
)

internal data class LiveEvidenceBinding(
    val farmEvidenceSha256: String,
    val gateSha256: String,
    val repairEvidenceSha256: String,
    val repairEvidenceCount: Int,
)

internal data class LiveCandidateProvider(
    val current: String,
    val candidate: String,
)

internal data class LiveApprovalCandidate(
    val candidateSetId: String,
    val state: String,
    val gateFingerprint: String,
    val providers: Map<String, LiveCandidateProvider>,
    val evidenceBinding: LiveEvidenceBinding,
    val publishEligible: Boolean,
)

internal data class LivePromotionState(
    val candidateSetId: String,
    val promotionRunId: Long,
    val providers: Map<String, String>,
    val evidenceBinding: LiveEvidenceBinding?,
    val publishEligible: Boolean,
)

internal data class LivePublishState(
    val candidateSetId: String,
    val signingRunId: Long,
    val publishRunId: Long,
    val releaseRunId: Long,
    val foundationCommit: String,
    val providers: Map<String, String>,
    val version: String,
    val tag: String,
)

internal data class LiveAutomationCandidate(
    val current: String,
    val candidate: String,
)

internal data class LiveAutomationState(
    val state: String,
    val reason: String,
    val ownerActionRequired: Boolean,
    val workflowRunId: Long?,
    val candidates: Map<String, LiveAutomationCandidate>,
)

internal data class LiveFarmRun(
    val id: Long,
    val runNumber: Int,
    val status: String,
    val conclusion: String?,
    val headSha: String,
    val title: String,
    val createdAt: String,
    val htmlUrl: String,
)

internal data class LivePendingWorkerState(
    val schemaVersion: Int,
    val readyCount: Int,
    val retryCount: Int,
    val needsAttentionCount: Int,
    val approvedCount: Int,
    val readyCanonicalIds: List<String>,
    val updatedAt: String?,
)

internal data class LiveFarmSnapshot(
    val sources: List<LiveSourceState>,
    val providers: List<LiveProviderState>,
    val recentRuns: List<LiveFarmRun>,
    val approvalCandidate: LiveApprovalCandidate?,
    val lastPromotion: LivePromotionState?,
    val lastPublish: LivePublishState?,
    val cohort: String,
    val targetSize: Int,
    val branch: String,
    val retrievedAtEpochMs: Long,
    val automation: LiveAutomationState? = null,
    val pendingWorker: LivePendingWorkerState? = null,
)

internal object SourceLabRepository {
    const val farmBranch = "compatibility-farm-foundation"

    private const val repository = "Noirero/Miyorare-Source-Packs"
    private const val rawBase =
        "https://raw.githubusercontent.com/$repository/$farmBranch"
    private const val apiBase = "https://api.github.com/repos/$repository"

    suspend fun loadSnapshot(): LiveFarmSnapshot = coroutineScope {
        // These resources are independent. Fetching them in parallel keeps the
        // dashboard bounded by the slowest GitHub request instead of the sum of
        // four network round-trips.
        val registryJob = async(Dispatchers.IO) {
            JSONObject(fetchText("$rawBase/compatibility/source-registry.json"))
        }
        val statusJob = async(Dispatchers.IO) {
            JSONObject(fetchText("$rawBase/upstream/status.json"))
        }
        val recentRunsJob = async(Dispatchers.IO) {
            runCatching { loadRecentFarmRuns() }.getOrDefault(emptyList())
        }
        val pendingWorkerJob = async(Dispatchers.IO) {
            runCatching { loadPendingWorkerState() }.getOrNull()
        }

        val registry = registryJob.await()
        val status = statusJob.await()

        val scope = registry.getJSONObject("scope")
        val sourceArray = registry.getJSONArray("sources")
        val sources = buildList {
            for (index in 0 until sourceArray.length()) {
                val source = sourceArray.getJSONObject(index)
                val providersJson = source.getJSONArray("providers")
                val providers = buildList {
                    for (providerIndex in 0 until providersJson.length()) {
                        add(providersJson.getString(providerIndex))
                    }
                }
                add(
                    LiveSourceState(
                        canonicalId = source.getString("canonicalId"),
                        displayName = source.getString("displayName"),
                        language = source.getString("language").uppercase(),
                        contentProfile = source.optString("contentProfile", "unknown"),
                        authType = source.optString("authType", "UNKNOWN"),
                        adapterFamily = source.optString("adapterFamily", "unknown"),
                        providers = providers,
                        updateState = source.optString("updateState", "UNKNOWN"),
                        runtimeHealth = source.optString("runtimeHealth", "UNKNOWN"),
                        approvalState = source.optString("approvalState", "NOT_READY"),
                    )
                )
            }
        }

        val providerObject = status.getJSONObject("providers")
        val providers = providerObject.keys().asSequence().map { providerId ->
            val provider = providerObject.getJSONObject(providerId)
            LiveProviderState(
                id = providerId,
                updateState = provider.optString("updateState", "UNKNOWN"),
                runtimeHealth = provider.optString("runtimeHealth", "UNKNOWN"),
                activeCommit = provider.optString("activeCommit", ""),
                lastKnownGood = provider.optString("lastKnownGood", ""),
                recoveryState = provider.optString("recoveryState", "UNKNOWN"),
                reason = provider.optString("reason").takeIf { it.isNotBlank() },
            )
        }.sortedBy { it.id }.toList()

        LiveFarmSnapshot(
            sources = sources,
            providers = providers,
            recentRuns = recentRunsJob.await(),
            approvalCandidate = status.optJSONObject("approvalCandidate")?.toApprovalCandidate(),
            lastPromotion = status.optJSONObject("lastPromotion")?.toPromotionState(),
            lastPublish = status.optJSONObject("lastPublish")?.toPublishState(),
            cohort = scope.optString("cohort", "unknown"),
            targetSize = scope.optInt("targetSize", sources.size),
            branch = farmBranch,
            retrievedAtEpochMs = System.currentTimeMillis(),
            automation = status.optJSONObject("automation")?.toAutomationState(),
            pendingWorker = pendingWorkerJob.await(),
        )
    }

    private fun JSONObject.toApprovalCandidate(): LiveApprovalCandidate {
        val providerObject = getJSONObject("providers")
        val providerMap = providerObject.keys().asSequence().associateWith { provider ->
            val item = providerObject.getJSONObject(provider)
            LiveCandidateProvider(
                current = item.getString("current"),
                candidate = item.getString("candidate"),
            )
        }
        return LiveApprovalCandidate(
            candidateSetId = getString("candidateSetId"),
            state = getString("state"),
            gateFingerprint = optString("gateFingerprint"),
            providers = providerMap.toSortedMap(),
            evidenceBinding = getJSONObject("evidenceBinding").toEvidenceBinding(),
            publishEligible = optBoolean("publishEligible", false),
        )
    }

    private fun JSONObject.toPromotionState(): LivePromotionState {
        val providerObject = getJSONObject("providers")
        val providerMap = providerObject.keys().asSequence().associateWith { provider ->
            providerObject.getString(provider)
        }
        return LivePromotionState(
            candidateSetId = getString("candidateSetId"),
            promotionRunId = getLong("promotionRunId"),
            providers = providerMap.toSortedMap(),
            evidenceBinding = optJSONObject("evidenceBinding")?.toEvidenceBinding(),
            publishEligible = optBoolean("publishEligible", false),
        )
    }

    private fun JSONObject.toPublishState(): LivePublishState {
        val providerObject = getJSONObject("providers")
        val providerMap = providerObject.keys().asSequence().associateWith { provider ->
            providerObject.getString(provider)
        }
        return LivePublishState(
            candidateSetId = getString("candidateSetId"),
            signingRunId = getLong("signingRunId"),
            publishRunId = getLong("publishRunId"),
            releaseRunId = getLong("releaseRunId"),
            foundationCommit = getString("foundationCommit"),
            providers = providerMap.toSortedMap(),
            version = getString("version"),
            tag = getString("tag"),
        )
    }

    private fun JSONObject.toAutomationState(): LiveAutomationState {
        val candidatesObject = optJSONObject("candidates")
        val candidates = if (candidatesObject == null) {
            emptyMap()
        } else {
            candidatesObject.keys().asSequence().mapNotNull { provider ->
                val item = candidatesObject.optJSONObject(provider) ?: return@mapNotNull null
                val current = item.optString("current")
                val candidate = item.optString("candidate")
                if (current.isBlank() || candidate.isBlank()) return@mapNotNull null
                provider to LiveAutomationCandidate(current = current, candidate = candidate)
            }.toMap().toSortedMap()
        }
        return LiveAutomationState(
            state = optString("state", "UNKNOWN"),
            reason = optString("reason", "UNKNOWN"),
            ownerActionRequired = optBoolean("ownerActionRequired", false),
            workflowRunId = optLong("workflowRunId", -1L).takeIf { it > 0L },
            candidates = candidates,
        )
    }

    private fun JSONObject.toEvidenceBinding() = LiveEvidenceBinding(
        farmEvidenceSha256 = getString("farmEvidenceSha256"),
        gateSha256 = getString("gateSha256"),
        repairEvidenceSha256 = getString("repairEvidenceSha256"),
        repairEvidenceCount = optInt("repairEvidenceCount", 0),
    )

    internal fun parsePendingWorkerState(root: JSONObject): LivePendingWorkerState {
        val schemaVersion = root.optInt("schemaVersion", -1)
        require(schemaVersion == 2) { "PENDING_WORKER_SCHEMA_UNSUPPORTED" }
        val sources = root.optJSONObject("sources") ?: JSONObject()
        var ready = 0
        var retry = 0
        var needsAttention = 0
        var approved = 0
        val readyIds = mutableListOf<String>()
        val keys = sources.keys()
        while (keys.hasNext()) {
            val canonicalId = keys.next()
            val state = sources.optJSONObject(canonicalId)?.optString("state").orEmpty()
            when (state) {
                "READY_FOR_APPROVAL" -> {
                    ready += 1
                    readyIds += canonicalId
                }
                "RETRY", "PARSER_PENDING" -> retry += 1
                "NEEDS_ATTENTION" -> needsAttention += 1
                "APPROVED" -> approved += 1
            }
        }
        return LivePendingWorkerState(
            schemaVersion = schemaVersion,
            readyCount = ready,
            retryCount = retry,
            needsAttentionCount = needsAttention,
            approvedCount = approved,
            readyCanonicalIds = readyIds.sorted(),
            updatedAt = root.optString("updatedAt").takeIf { it.isNotBlank() },
        )
    }

    private fun loadPendingWorkerState(): LivePendingWorkerState =
        parsePendingWorkerState(JSONObject(fetchText("$rawBase/automation/pending-worker-state.json")))

    private fun loadRecentFarmRuns(): List<LiveFarmRun> {
        val url = "$apiBase/actions/workflows/source-lab-auto-farm.yml/runs?branch=main&per_page=5"
        val payload = JSONObject(fetchText(url))
        val runs = payload.getJSONArray("workflow_runs")
        return buildList {
            for (index in 0 until runs.length()) {
                val run = runs.getJSONObject(index)
                add(
                    LiveFarmRun(
                        id = run.getLong("id"),
                        runNumber = run.optInt("run_number"),
                        status = run.optString("status", "unknown"),
                        conclusion = run.optString("conclusion").takeIf { it.isNotBlank() && it != "null" },
                        headSha = run.optString("head_sha"),
                        title = run.optString("display_title", "Compatibility Farm"),
                        createdAt = run.optString("created_at"),
                        htmlUrl = run.optString("html_url"),
                    )
                )
            }
        }
    }

    private fun fetchText(url: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/0.1.8")
            useCaches = false
        }

        return try {
            val statusCode = connection.responseCode
            if (statusCode !in 200..299) {
                error("HTTP $statusCode while reading Compatibility Farm data")
            }
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }
}
