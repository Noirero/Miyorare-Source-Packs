package com.noirero.miyorare.sourcelab

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

internal data class P3AudioRuntime(
    val id: String,
    val name: String,
    val version: String,
    val auth: String,
    val languages: List<String>,
    val capabilities: List<String>,
    val deliveryKind: String,
)

internal data class P3AudioCatalogSnapshot(
    val sourcePackCommit: String,
    val miyorareCatalogCommit: String,
    val hiraukanRuntimeCommit: String,
    val runtimes: List<P3AudioRuntime>,
    val releaseEligibility: String,
    val releaseEligibilityReason: String,
    val miyorareBetaMerged: Boolean,
    val deviceValidationState: String,
    val deviceValidationRequiredForRelease: Boolean,
    val deviceValidated: Boolean,
    val deviceValidationNote: String,
)

internal data class P3AudioCatalogBaseline(
    val sourcePackCommit: String,
    val miyorareCatalogCommit: String,
    val miyorareCatalogPath: String,
    val hiraukanRuntimeCommit: String,
    val expectedRuntimeIds: List<String>,
    val releaseEligibility: String,
    val releaseEligibilityReason: String,
    val miyorareBetaMerged: Boolean,
    val deviceValidationState: String,
    val deviceValidationRequiredForRelease: Boolean,
    val deviceValidated: Boolean,
    val deviceValidationNote: String,
)

internal object P3AudioCatalogRepository {
    private const val sourcePackRepository = "Noirero/Miyorare-Source-Packs"
    private const val sourcePackApi = "https://api.github.com/repos/$sourcePackRepository"
    private const val sourcePackMainBranch = "main"
    private const val baselinePath = "compatibility/miyorare-audio-catalog-baseline.json"
    private const val miyorareRepository = "Noirero/Miyorare"
    private const val hiraukanRepository = "Noirero/Hiraukan"
    private const val catalogPath = "extensions/miyorare-audio/pack.json"
    private const val catalogValidatorPath = "extensions/miyorare-audio/tools/validate_pack.py"
    private const val hiraukanRegistryPath = "lib/src/extensions/audio_extension_provider.dart"

    private val gitCommitPattern = Regex("^[0-9a-f]{40}$")
    private val exactRuntimeIds = setOf(
        "miyorare.audio.asmr_one",
        "miyorare.audio.hentai_asmr",
        "miyorare.audio.japanese_asmr",
        "miyorare.audio.asmr18",
        "miyorare.audio.ero_voice",
        "miyorare.audio.asmr_hentai_net",
    )

    suspend fun loadSnapshot(): P3AudioCatalogSnapshot = withContext(Dispatchers.IO) {
        val sourcePackCommit = parseMainBranchHead(
            JSONObject(fetchText("$sourcePackApi/branches/$sourcePackMainBranch")),
        )
        val baseline = parseBaseline(
            JSONObject(fetchText(sourcePackRawUrl(sourcePackCommit, baselinePath))),
            sourcePackCommit,
        )
        val runtimes = parseCatalog(
            JSONObject(
                fetchText(
                    "https://raw.githubusercontent.com/$miyorareRepository/" +
                        "${baseline.miyorareCatalogCommit}/${baseline.miyorareCatalogPath}",
                ),
            ),
            baseline.expectedRuntimeIds,
        )

        P3AudioCatalogSnapshot(
            sourcePackCommit = baseline.sourcePackCommit,
            miyorareCatalogCommit = baseline.miyorareCatalogCommit,
            hiraukanRuntimeCommit = baseline.hiraukanRuntimeCommit,
            runtimes = runtimes,
            releaseEligibility = baseline.releaseEligibility,
            releaseEligibilityReason = baseline.releaseEligibilityReason,
            miyorareBetaMerged = baseline.miyorareBetaMerged,
            deviceValidationState = baseline.deviceValidationState,
            deviceValidationRequiredForRelease = baseline.deviceValidationRequiredForRelease,
            deviceValidated = baseline.deviceValidated,
            deviceValidationNote = baseline.deviceValidationNote,
        )
    }

    internal fun parseMainBranchHead(root: JSONObject): String {
        val commit = root.getJSONObject("commit").getString("sha").lowercase()
        require(gitCommitPattern.matches(commit)) { "P3_MAIN_HEAD_INVALID" }
        return commit
    }

    internal fun sourcePackRawUrl(commit: String, path: String): String {
        require(gitCommitPattern.matches(commit)) { "P3_SOURCE_PACK_COMMIT_INVALID" }
        require(path.isNotBlank() && !path.startsWith('/') && path.split('/').none { it == ".." }) {
            "P3_SOURCE_PACK_PATH_INVALID"
        }
        return "https://raw.githubusercontent.com/$sourcePackRepository/$commit/$path"
    }

    internal fun parseBaseline(root: JSONObject, sourcePackCommit: String): P3AudioCatalogBaseline {
        require(gitCommitPattern.matches(sourcePackCommit)) { "P3_SOURCE_PACK_COMMIT_INVALID" }
        require(root.optInt("schemaVersion", -1) == 1) { "P3_BASELINE_SCHEMA_UNSUPPORTED" }
        require(root.optString("kind") == "MIYORARE_AUDIO_CATALOG_BASELINE") { "P3_BASELINE_KIND_INVALID" }

        val miyorare = root.getJSONObject("miyorare")
        require(miyorare.getString("repository") == miyorareRepository) { "P3_MIYORARE_REPOSITORY_INVALID" }
        require(miyorare.getString("lineageBranch") == "beta") { "P3_MIYORARE_LINEAGE_INVALID" }
        val miyorareCommit = exactSha(miyorare.getString("catalogCommit"), "P3_MIYORARE_COMMIT_INVALID")
        require(miyorare.getString("catalogPath") == catalogPath) { "P3_CATALOG_PATH_INVALID" }
        require(miyorare.getString("validatorPath") == catalogValidatorPath) { "P3_CATALOG_VALIDATOR_PATH_INVALID" }
        require(miyorare.optInt("sourcePullRequest", 0) > 0) { "P3_SOURCE_PR_INVALID" }

        val hiraukan = root.getJSONObject("hiraukan")
        require(hiraukan.getString("repository") == hiraukanRepository) { "P3_HIRAUKAN_REPOSITORY_INVALID" }
        require(hiraukan.getString("lineageBranch") == "beta") { "P3_HIRAUKAN_LINEAGE_INVALID" }
        val hiraukanCommit = exactSha(hiraukan.getString("runtimeCommit"), "P3_HIRAUKAN_COMMIT_INVALID")
        require(hiraukan.getString("runtimeRegistryPath") == hiraukanRegistryPath) { "P3_RUNTIME_REGISTRY_PATH_INVALID" }

        val runtimeIds = readStringList(root.getJSONArray("expectedRuntimeIds"), "P3_RUNTIME_IDS_INVALID")
        require(runtimeIds.size == runtimeIds.toSet().size) { "P3_RUNTIME_IDS_DUPLICATED" }
        require(runtimeIds.toSet() == exactRuntimeIds) { "P3_RUNTIME_SET_INVALID" }

        val device = root.getJSONObject("deviceValidation")
        val deviceState = device.getString("state")
        val requiredForRelease = device.getBoolean("requiredForRelease")
        val validated = device.getBoolean("validated")
        val note = device.getString("note")
        require(deviceState in setOf("REQUIRED", "VALIDATED", "DEFERRED_BY_OWNER")) { "P3_DEVICE_STATE_INVALID" }
        require(note.isNotBlank()) { "P3_DEVICE_NOTE_REQUIRED" }
        if (deviceState == "VALIDATED") {
            require(validated) { "P3_DEVICE_VALIDATED_FLAG_INVALID" }
        }
        if (deviceState == "DEFERRED_BY_OWNER") {
            require(!requiredForRelease && !validated) { "P3_DEVICE_DEFERRED_FLAGS_INVALID" }
        }
        if (deviceState == "REQUIRED") {
            require(requiredForRelease) { "P3_DEVICE_REQUIRED_FLAG_INVALID" }
        }

        val eligibility = root.getJSONObject("releaseEligibility")
        val releaseState = eligibility.getString("state")
        val betaMerged = eligibility.getBoolean("miyorareBetaMerged")
        val reason = eligibility.getString("reason")
        require(releaseState in setOf("BLOCKED", "ELIGIBLE")) { "P3_RELEASE_STATE_INVALID" }
        require(reason.isNotBlank()) { "P3_RELEASE_REASON_REQUIRED" }
        if (releaseState == "ELIGIBLE") {
            require(betaMerged) { "P3_ELIGIBLE_REQUIRES_BETA_MERGE" }
        }
        require(!(requiredForRelease && !validated && releaseState == "ELIGIBLE")) {
            "P3_ELIGIBLE_BYPASSES_REQUIRED_DEVICE_VALIDATION"
        }
        require(!(releaseState == "BLOCKED" && betaMerged && (!requiredForRelease || validated))) {
            "P3_BLOCKED_WITHOUT_DECLARED_GATE"
        }

        return P3AudioCatalogBaseline(
            sourcePackCommit = sourcePackCommit,
            miyorareCatalogCommit = miyorareCommit,
            miyorareCatalogPath = catalogPath,
            hiraukanRuntimeCommit = hiraukanCommit,
            expectedRuntimeIds = runtimeIds,
            releaseEligibility = releaseState,
            releaseEligibilityReason = reason,
            miyorareBetaMerged = betaMerged,
            deviceValidationState = deviceState,
            deviceValidationRequiredForRelease = requiredForRelease,
            deviceValidated = validated,
            deviceValidationNote = note,
        )
    }

    internal fun parseCatalog(root: JSONObject, expectedRuntimeIds: List<String>): List<P3AudioRuntime> {
        require(expectedRuntimeIds.toSet() == exactRuntimeIds && expectedRuntimeIds.size == exactRuntimeIds.size) {
            "P3_EXPECTED_RUNTIME_SET_INVALID"
        }
        require(root.optInt("schemaVersion", -1) == 1) { "P3_CATALOG_SCHEMA_UNSUPPORTED" }
        require(root.optString("packId") == "miyorare-audio") { "P3_CATALOG_PACK_ID_INVALID" }
        require(root.optString("mediaType") == "audio") { "P3_CATALOG_MEDIA_TYPE_INVALID" }

        val consumer = root.getJSONObject("consumer")
        require(consumer.getString("application") == "Hiraukan") { "P3_CATALOG_CONSUMER_INVALID" }
        require(consumer.getString("repository") == hiraukanRepository) { "P3_CATALOG_CONSUMER_REPOSITORY_INVALID" }
        require(consumer.optInt("extensionSchemaVersion", -1) == 1) { "P3_EXTENSION_SCHEMA_UNSUPPORTED" }

        val extensions = root.getJSONArray("extensions")
        require(extensions.length() == exactRuntimeIds.size) { "P3_CATALOG_RUNTIME_COUNT_INVALID" }
        val byId = linkedMapOf<String, P3AudioRuntime>()
        for (index in 0 until extensions.length()) {
            val item = extensions.getJSONObject(index)
            val id = item.getString("id")
            require(id.isNotBlank() && id in exactRuntimeIds) { "P3_CATALOG_RUNTIME_ID_INVALID" }
            require(id !in byId) { "P3_CATALOG_RUNTIME_ID_DUPLICATED" }
            require(item.getString("type") == "audio") { "P3_CATALOG_RUNTIME_TYPE_INVALID" }
            val name = item.getString("name")
            val version = item.getString("version")
            val auth = item.getString("auth")
            require(name.isNotBlank() && version.isNotBlank() && auth.isNotBlank()) { "P3_CATALOG_RUNTIME_METADATA_INVALID" }
            val languages = readStringList(item.getJSONArray("languages"), "P3_CATALOG_LANGUAGES_INVALID")
            val capabilities = readStringList(item.getJSONArray("capabilities"), "P3_CATALOG_CAPABILITIES_INVALID")
            require(languages.isNotEmpty()) { "P3_CATALOG_LANGUAGES_EMPTY" }
            require(capabilities.isNotEmpty()) { "P3_CATALOG_CAPABILITIES_EMPTY" }
            val delivery = item.getJSONObject("delivery")
            require(delivery.getString("kind") == "builtin") { "P3_CATALOG_DELIVERY_NOT_BUILTIN" }
            require(delivery.getString("runtimeId") == id) { "P3_CATALOG_RUNTIME_BINDING_INVALID" }
            byId[id] = P3AudioRuntime(
                id = id,
                name = name,
                version = version,
                auth = auth,
                languages = languages,
                capabilities = capabilities,
                deliveryKind = "builtin",
            )
        }
        require(byId.keys == exactRuntimeIds) { "P3_CATALOG_RUNTIME_SET_INVALID" }
        return expectedRuntimeIds.map { id -> byId.getValue(id) }
    }

    private fun readStringList(array: JSONArray, errorCode: String): List<String> = buildList {
        for (index in 0 until array.length()) {
            val value = array.getString(index)
            require(value.isNotBlank()) { errorCode }
            add(value)
        }
    }

    private fun exactSha(value: String, errorCode: String): String {
        val normalized = value.lowercase()
        require(gitCommitPattern.matches(normalized)) { errorCode }
        return normalized
    }

    private fun fetchText(url: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/1.2.15")
            useCaches = false
        }
        return try {
            val statusCode = connection.responseCode
            if (statusCode !in 200..299) {
                error("HTTP $statusCode while reading P3 Audio Catalog authority")
            }
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }
}
