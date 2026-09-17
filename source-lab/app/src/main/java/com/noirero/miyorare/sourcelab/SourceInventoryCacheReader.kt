package com.noirero.miyorare.sourcelab

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

/**
 * Fast, network-free cache read used by the UI for stale-while-revalidate.
 * SourceInventoryRepository remains the authority for validation and live refresh.
 */
internal object SourceInventoryCacheReader {
    private const val cacheDirectory = "source-inventory-cache"
    private const val cachePayloadName = "source-inventory.json"
    private const val cacheMetadataName = "metadata.json"

    suspend fun load(context: Context): SourceInventorySnapshot? = withContext(Dispatchers.IO) {
        val directory = File(context.cacheDir, cacheDirectory)
        val payloadFile = File(directory, cachePayloadName)
        val metadataFile = File(directory, cacheMetadataName)
        if (!payloadFile.isFile || !metadataFile.isFile) return@withContext null

        runCatching {
            val metadata = JSONObject(metadataFile.readText())
            val commit = metadata.getString("commit")
            val savedAt = metadata.getLong("savedAtEpochMs")
            require(commit.matches(Regex("^[0-9a-f]{40}$")))
            val now = System.currentTimeMillis()
            SourceInventoryRepository.parseInventory(
                payload = payloadFile.readText(),
                branchCommit = commit,
                retrievedAtEpochMs = savedAt,
                fromCache = true,
                cacheAgeMillis = (now - savedAt).coerceAtLeast(0L),
            )
        }.getOrNull()
    }
}
