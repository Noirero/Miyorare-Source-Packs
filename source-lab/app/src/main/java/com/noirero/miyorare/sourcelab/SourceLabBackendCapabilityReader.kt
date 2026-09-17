package com.noirero.miyorare.sourcelab

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets
import java.util.zip.ZipInputStream

/**
 * Reads the capability list from the same short-lived workflow artifact whose
 * OIDC JWT has already been verified by [SourceLabBackendAuthorization].
 *
 * Schema v1 keeps the original five capabilities in `capabilities` for older
 * installed Source Lab versions. Newer, independently gated capabilities are
 * advertised in `optionalCapabilities`; unknown optional values are ignored so
 * future backend additions do not break an older client, while they never grant
 * a capability unless this APK explicitly recognizes the enum value.
 */
internal object SourceLabBackendCapabilityReader {
    private const val repository = SourceLabAccessPolicy.repository
    private const val apiBase = "https://api.github.com/repos/$repository"

    suspend fun read(
        githubAccessToken: String,
        proof: BackendAuthorizationProof,
    ): Set<SourceLabControlAction> = withContext(Dispatchers.IO) {
        require(proof.authorized) { "BACKEND_PROOF_NOT_AUTHORIZED" }
        val runId = requireNotNull(proof.runId) { "BACKEND_PROOF_RUN_MISSING" }
        val challenge = requireNotNull(proof.challenge) { "BACKEND_PROOF_CHALLENGE_MISSING" }

        val artifacts = JSONObject(
            request(
                "$apiBase/actions/runs/$runId/artifacts?per_page=20",
                githubAccessToken,
            ),
        ).getJSONArray("artifacts")
        val expectedName = "source-lab-authorization-$challenge"
        var downloadUrl: String? = null
        for (index in 0 until artifacts.length()) {
            val artifact = artifacts.getJSONObject(index)
            if (artifact.optString("name") != expectedName) continue
            if (artifact.optBoolean("expired", false)) error("BACKEND_CAPABILITY_ARTIFACT_EXPIRED")
            downloadUrl = artifact.getString("archive_download_url")
            break
        }
        val archive = downloadArtifact(
            githubAccessToken,
            downloadUrl ?: error("BACKEND_CAPABILITY_ARTIFACT_MISSING"),
        )
        val metadataBytes = unzipMetadata(archive)
            ?: error("BACKEND_CAPABILITY_METADATA_MISSING")
        val metadata = JSONObject(String(metadataBytes, StandardCharsets.UTF_8))

        require(metadata.optInt("schemaVersion", -1) == 1) { "BACKEND_CAPABILITY_SCHEMA_MISMATCH" }
        require(metadata.optString("challenge") == challenge) { "BACKEND_CAPABILITY_CHALLENGE_MISMATCH" }
        require(metadata.optString("repository") == repository) { "BACKEND_CAPABILITY_REPOSITORY_MISMATCH" }
        require(metadata.optString("actorId") == SourceLabAccessPolicy.ownerGithubUserId.toString()) {
            "BACKEND_CAPABILITY_ACTOR_MISMATCH"
        }
        require(metadata.optString("runId") == runId.toString()) { "BACKEND_CAPABILITY_RUN_MISMATCH" }
        require(metadata.optString("ref") == "refs/heads/main") { "BACKEND_CAPABILITY_REF_MISMATCH" }
        require(metadata.optString("event") == "workflow_dispatch") { "BACKEND_CAPABILITY_EVENT_MISMATCH" }

        parseCapabilityMetadata(metadata)
    }

    internal fun parseCapabilityMetadata(metadata: JSONObject): Set<SourceLabControlAction> {
        val raw = metadata.optJSONArray("capabilities")
            ?: error("BACKEND_CAPABILITIES_MISSING")
        val capabilities = mutableSetOf<SourceLabControlAction>()
        for (index in 0 until raw.length()) {
            val value = raw.optString(index)
            val action = SourceLabControlAction.entries.firstOrNull { it.name == value }
                ?: error("BACKEND_CAPABILITY_UNKNOWN_$value")
            capabilities += action
        }

        val optional = metadata.optJSONArray("optionalCapabilities")
        if (optional != null) {
            for (index in 0 until optional.length()) {
                val value = optional.optString(index)
                val action = SourceLabControlAction.entries.firstOrNull { it.name == value }
                if (action != null) capabilities += action
            }
        }
        return capabilities.toSet()
    }

    private fun request(url: String, token: String): String {
        val connection = open(url, token).apply { requestMethod = "GET" }
        return try {
            val code = connection.responseCode
            if (code !in 200..299) error("BACKEND_CAPABILITY_HTTP_$code")
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun downloadArtifact(token: String, apiUrl: String): ByteArray {
        val first = open(apiUrl, token).apply {
            requestMethod = "GET"
            instanceFollowRedirects = false
        }
        try {
            val code = first.responseCode
            if (code !in 300..399) {
                if (code !in 200..299) error("BACKEND_CAPABILITY_ARTIFACT_HTTP_$code")
                return first.inputStream.use { it.readBytesLimited(1_048_576) }
            }
            val location = first.getHeaderField("Location")
                ?: error("BACKEND_CAPABILITY_ARTIFACT_REDIRECT_MISSING")
            val second = (URL(location).openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 10_000
                readTimeout = 15_000
                instanceFollowRedirects = true
                useCaches = false
            }
            return try {
                val secondCode = second.responseCode
                if (secondCode !in 200..299) error("BACKEND_CAPABILITY_ARTIFACT_HTTP_$secondCode")
                second.inputStream.use { it.readBytesLimited(1_048_576) }
            } finally {
                second.disconnect()
            }
        } finally {
            first.disconnect()
        }
    }

    private fun unzipMetadata(archive: ByteArray): ByteArray? {
        ZipInputStream(ByteArrayInputStream(archive)).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                if (!entry.isDirectory && entry.name.substringAfterLast('/') == "metadata.json") {
                    return zip.readBytesLimited(256 * 1024)
                }
                zip.closeEntry()
            }
        }
        return null
    }

    private fun open(url: String, token: String): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/${BuildConfig.VERSION_NAME}")
            useCaches = false
        }

    private fun java.io.InputStream.readBytesLimited(limit: Int): ByteArray {
        val buffer = ByteArray(8 * 1024)
        val output = java.io.ByteArrayOutputStream()
        var total = 0
        while (true) {
            val read = read(buffer)
            if (read < 0) break
            total += read
            require(total <= limit) { "BACKEND_CAPABILITY_RESPONSE_TOO_LARGE" }
            output.write(buffer, 0, read)
        }
        return output.toByteArray()
    }
}
