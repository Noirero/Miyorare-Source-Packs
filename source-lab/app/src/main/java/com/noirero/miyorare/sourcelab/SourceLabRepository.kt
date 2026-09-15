package com.noirero.miyorare.sourcelab

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

internal data class LiveFarmSnapshot(
    val sources: List<LiveSourceState>,
    val providers: List<LiveProviderState>,
    val recentRuns: List<LiveFarmRun>,
    val cohort: String,
    val targetSize: Int,
    val branch: String,
    val retrievedAtEpochMs: Long,
)

internal object SourceLabRepository {
    const val farmBranch = "compatibility-farm-foundation"

    private const val repository = "Noirero/Miyorare-Source-Packs"
    private const val rawBase =
        "https://raw.githubusercontent.com/$repository/$farmBranch"
    private const val apiBase = "https://api.github.com/repos/$repository"

    fun loadSnapshot(): LiveFarmSnapshot {
        val registry = JSONObject(fetchText("$rawBase/compatibility/source-registry.json"))
        val status = JSONObject(fetchText("$rawBase/upstream/status.json"))

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

        // Workflow history is supplemental. A GitHub API/rate-limit failure must not
        // hide the registry/runtime snapshot that is still available from raw content.
        val recentRuns = runCatching { loadRecentFarmRuns() }.getOrDefault(emptyList())

        return LiveFarmSnapshot(
            sources = sources,
            providers = providers,
            recentRuns = recentRuns,
            cohort = scope.optString("cohort", "unknown"),
            targetSize = scope.optInt("targetSize", sources.size),
            branch = farmBranch,
            retrievedAtEpochMs = System.currentTimeMillis(),
        )
    }

    private fun loadRecentFarmRuns(): List<LiveFarmRun> {
        val url = "$apiBase/actions/workflows/compatibility-farm-accelerated.yml/runs" +
            "?branch=$farmBranch&per_page=5"
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
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/0.1")
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
