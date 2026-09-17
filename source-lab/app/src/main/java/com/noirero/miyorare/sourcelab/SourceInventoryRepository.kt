package com.noirero.miyorare.sourcelab

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

internal data class InventoryProviderMapping(
    val provider: String,
    val available: Boolean,
    val sourceName: String?,
    val displayName: String?,
    val sourceId: Long?,
    val module: String?,
    val file: String?,
    val baseUrl: String?,
    val extensionVersionCode: Int?,
)

internal data class InventorySource(
    val canonicalId: String,
    val displayName: String,
    val language: String,
    val identityConfidence: String,
    val needsAttention: Boolean,
    val attentionReasons: List<String>,
    val providers: Map<String, InventoryProviderMapping>,
)

internal data class InventoryRepairPolicy(
    val autoDiagnose: Boolean,
    val safeSelfRepair: Boolean,
    val keepLastKnownGood: Boolean,
    val validatedCanonicalFallback: Boolean,
)

internal data class FarmInventorySourceState(
    val canonicalId: String,
    val contentProfile: String,
    val authType: String,
    val adapterFamily: String,
    val updateState: String,
    val runtimeHealth: String,
    val approvalState: String,
    val ownerActionRequired: Boolean,
    val publishEligible: Boolean,
    val currentVersion: Map<String, String>,
    val lastKnownGood: Map<String, String>,
    val repairPolicy: InventoryRepairPolicy?,
)

internal data class FarmInventorySnapshot(
    val sources: List<FarmInventorySourceState>,
    val branch: String,
    val retrievedAtEpochMs: Long,
)

internal data class SourceInventorySnapshot(
    val sources: List<InventorySource>,
    val providerCommits: Map<String, String>,
    val branch: String,
    val retrievedAtEpochMs: Long,
) {
    fun summary(farmCanonicalIds: Set<String>): SourceInventorySummary {
        val inFarm = sources.count { it.canonicalId in farmCanonicalIds }
        return SourceInventorySummary(
            allSources = sources.size,
            inFarm = inFarm,
            notEnrolled = sources.size - inFarm,
            needsAttention = sources.count { it.needsAttention },
        )
    }
}

internal data class SourceInventorySummary(
    val allSources: Int,
    val inFarm: Int,
    val notEnrolled: Int,
    val needsAttention: Int,
)

internal object SourceInventoryRepository {
    const val inventoryBranch = "source-inventory-live"

    private const val repository = "Noirero/Miyorare-Source-Packs"
    private const val inventoryUrl =
        "https://raw.githubusercontent.com/$repository/$inventoryBranch/inventory/source-inventory.json"
    private const val farmUrl =
        "https://raw.githubusercontent.com/$repository/${SourceLabRepository.farmBranch}/compatibility/source-registry.json"

    suspend fun loadInventory(): SourceInventorySnapshot = withContext(Dispatchers.IO) {
        parseInventory(fetchText(inventoryUrl))
    }

    suspend fun loadFarmMembership(): FarmInventorySnapshot = withContext(Dispatchers.IO) {
        parseFarmRegistry(fetchText(farmUrl))
    }

    internal fun parseInventory(payload: String): SourceInventorySnapshot {
        val root = JSONObject(payload)
        require(root.optInt("schemaVersion") == 1) { "Unsupported source inventory schema" }
        require(root.optString("kind") == "MIYORARE_SOURCE_INVENTORY") { "Invalid source inventory kind" }
        require(root.optBoolean("informationalOnly", false)) { "Source inventory must be informational only" }

        val providerCommits = buildMap {
            val snapshots = root.optJSONObject("providerSnapshots") ?: JSONObject()
            snapshots.keys().asSequence().forEach { provider ->
                val commit = snapshots.optJSONObject(provider)?.optString("commit").orEmpty()
                if (commit.isNotBlank()) put(provider, commit)
            }
        }

        val seen = mutableSetOf<String>()
        val sourceArray = root.getJSONArray("sources")
        val sources = buildList {
            for (index in 0 until sourceArray.length()) {
                val source = sourceArray.getJSONObject(index)
                val canonicalId = source.getString("canonicalId")
                require(canonicalId.startsWith("miyorare:")) { "Invalid canonical source identity" }
                require(seen.add(canonicalId)) { "Duplicate canonical source identity" }

                val providerObject = source.getJSONObject("providers")
                val providers = providerObject.keys().asSequence().associateWith { provider ->
                    providerObject.getJSONObject(provider).toProviderMapping(provider)
                }.toSortedMap()
                require(providers.isNotEmpty()) { "Source has no provider mapping" }

                val reasonsJson = source.optJSONArray("attentionReasons")
                val reasons = buildList {
                    if (reasonsJson != null) {
                        for (reasonIndex in 0 until reasonsJson.length()) {
                            add(reasonsJson.getString(reasonIndex))
                        }
                    }
                }

                add(
                    InventorySource(
                        canonicalId = canonicalId,
                        displayName = source.optString("displayName").ifBlank { canonicalId.substringAfterLast(':') },
                        language = source.optString("language", "unknown").uppercase(),
                        identityConfidence = source.optString("identityConfidence", "unknown"),
                        needsAttention = source.optBoolean("needsAttention", false),
                        attentionReasons = reasons,
                        providers = providers,
                    )
                )
            }
        }.sortedWith(compareBy(String.CASE_INSENSITIVE_ORDER) { it.displayName })

        return SourceInventorySnapshot(
            sources = sources,
            providerCommits = providerCommits,
            branch = inventoryBranch,
            retrievedAtEpochMs = System.currentTimeMillis(),
        )
    }

    internal fun parseFarmRegistry(payload: String): FarmInventorySnapshot {
        val root = JSONObject(payload)
        require(root.optInt("schemaVersion") == 1) { "Unsupported Farm registry schema" }
        val defaults = root.optJSONObject("defaults") ?: JSONObject()
        val sourceArray = root.getJSONArray("sources")
        val sources = buildList {
            for (index in 0 until sourceArray.length()) {
                val source = sourceArray.getJSONObject(index)
                val repair = source.optJSONObject("repairPolicy") ?: defaults.optJSONObject("repairPolicy")
                add(
                    FarmInventorySourceState(
                        canonicalId = source.getString("canonicalId"),
                        contentProfile = source.optString("contentProfile", "unknown"),
                        authType = source.optString("authType", "UNKNOWN"),
                        adapterFamily = source.optString("adapterFamily", "unknown"),
                        updateState = source.optString("updateState", defaults.optString("updateState", "UNKNOWN")),
                        runtimeHealth = source.optString("runtimeHealth", defaults.optString("runtimeHealth", "UNKNOWN")),
                        approvalState = source.optString("approvalState", defaults.optString("approvalState", "NOT_READY")),
                        ownerActionRequired = source.optBoolean(
                            "ownerActionRequired",
                            defaults.optBoolean("ownerActionRequired", false),
                        ),
                        publishEligible = source.optBoolean("publishEligible", false),
                        currentVersion = source.optJSONObject("currentVersion").toStringMap(),
                        lastKnownGood = source.optJSONObject("lastKnownGood").toStringMap(),
                        repairPolicy = repair?.let {
                            InventoryRepairPolicy(
                                autoDiagnose = it.optBoolean("autoDiagnose", false),
                                safeSelfRepair = it.optBoolean("safeSelfRepair", false),
                                keepLastKnownGood = it.optBoolean("keepLastKnownGood", false),
                                validatedCanonicalFallback = it.optBoolean("validatedCanonicalFallback", false),
                            )
                        },
                    )
                )
            }
        }
        return FarmInventorySnapshot(
            sources = sources,
            branch = SourceLabRepository.farmBranch,
            retrievedAtEpochMs = System.currentTimeMillis(),
        )
    }

    private fun JSONObject?.toStringMap(): Map<String, String> {
        if (this == null) return emptyMap()
        return keys().asSequence()
            .associateWith { key -> optString(key) }
            .filterValues { it.isNotBlank() }
            .toSortedMap()
    }

    private fun JSONObject.toProviderMapping(provider: String): InventoryProviderMapping =
        InventoryProviderMapping(
            provider = provider,
            available = optBoolean("available", true),
            sourceName = optString("sourceName").takeIf { it.isNotBlank() },
            displayName = optString("displayName").takeIf { it.isNotBlank() },
            sourceId = if (has("sourceId") && !isNull("sourceId")) optLong("sourceId") else null,
            module = optString("module").takeIf { it.isNotBlank() },
            file = optString("file").takeIf { it.isNotBlank() },
            baseUrl = optString("baseUrl").takeIf { it.isNotBlank() },
            extensionVersionCode = if (has("extensionVersionCode") && !isNull("extensionVersionCode")) {
                optInt("extensionVersionCode")
            } else {
                null
            },
        )

    private fun fetchText(url: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/${BuildConfig.VERSION_NAME}")
            useCaches = false
        }
        return try {
            val statusCode = connection.responseCode
            if (statusCode !in 200..299) {
                error("HTTP $statusCode while reading Source Inventory")
            }
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }
}
