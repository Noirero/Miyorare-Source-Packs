package com.noirero.miyorare.sourcelab

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class P3AudioCatalogRepositoryTest {
    private val sourcePackCommit = "a".repeat(40)
    private val miyorareCommit = "b".repeat(40)
    private val hiraukanCommit = "c".repeat(40)
    private val runtimeIds = listOf(
        "miyorare.audio.asmr_one",
        "miyorare.audio.hentai_asmr",
        "miyorare.audio.japanese_asmr",
        "miyorare.audio.asmr18",
        "miyorare.audio.ero_voice",
        "miyorare.audio.asmr_hentai_net",
    )

    @Test
    fun currentP3BaselineKeepsDeferredDeviceValidationSeparateFromEligibility() {
        val baseline = P3AudioCatalogRepository.parseBaseline(validBaseline(), sourcePackCommit)

        assertEquals(sourcePackCommit, baseline.sourcePackCommit)
        assertEquals(miyorareCommit, baseline.miyorareCatalogCommit)
        assertEquals(hiraukanCommit, baseline.hiraukanRuntimeCommit)
        assertEquals(runtimeIds.toSet(), baseline.expectedRuntimeIds.toSet())
        assertEquals("ELIGIBLE", baseline.releaseEligibility)
        assertEquals("FINAL_MIYORARE_BETA_MERGED", baseline.releaseEligibilityReason)
        assertTrue(baseline.miyorareBetaMerged)
        assertEquals("DEFERRED_BY_OWNER", baseline.deviceValidationState)
        assertFalse(baseline.deviceValidationRequiredForRelease)
        assertFalse(baseline.deviceValidated)
    }

    @Test
    fun catalogRequiresExactlySixBuiltinRuntimeBindings() {
        val runtimes = P3AudioCatalogRepository.parseCatalog(validCatalog(), runtimeIds)

        assertEquals(6, runtimes.size)
        assertEquals(runtimeIds, runtimes.map { it.id })
        assertTrue(runtimes.all { it.deliveryKind == "builtin" })
        assertTrue(runtimes.all { it.languages.isNotEmpty() && it.capabilities.isNotEmpty() })
    }

    @Test(expected = IllegalArgumentException::class)
    fun unsupportedBaselineSchemaFailsClosed() {
        val baseline = validBaseline().put("schemaVersion", 2)

        P3AudioCatalogRepository.parseBaseline(baseline, sourcePackCommit)
    }

    @Test(expected = IllegalArgumentException::class)
    fun unsupportedCatalogSchemaFailsClosed() {
        val catalog = validCatalog().put("schemaVersion", 2)

        P3AudioCatalogRepository.parseCatalog(catalog, runtimeIds)
    }

    @Test(expected = IllegalArgumentException::class)
    fun eligibleBaselineCannotBypassRequiredDeviceValidation() {
        val baseline = validBaseline()
        baseline.getJSONObject("deviceValidation")
            .put("state", "REQUIRED")
            .put("requiredForRelease", true)
            .put("validated", false)

        P3AudioCatalogRepository.parseBaseline(baseline, sourcePackCommit)
    }

    @Test(expected = IllegalArgumentException::class)
    fun missingRuntimeFailsClosed() {
        val catalog = validCatalog()
        val extensions = catalog.getJSONArray("extensions")
        extensions.remove(extensions.length() - 1)

        P3AudioCatalogRepository.parseCatalog(catalog, runtimeIds)
    }

    @Test(expected = IllegalArgumentException::class)
    fun nonBuiltinDeliveryFailsClosed() {
        val catalog = validCatalog()
        catalog.getJSONArray("extensions")
            .getJSONObject(0)
            .getJSONObject("delivery")
            .put("kind", "download")

        P3AudioCatalogRepository.parseCatalog(catalog, runtimeIds)
    }

    @Test(expected = IllegalArgumentException::class)
    fun runtimeIdBindingMismatchFailsClosed() {
        val catalog = validCatalog()
        catalog.getJSONArray("extensions")
            .getJSONObject(0)
            .getJSONObject("delivery")
            .put("runtimeId", runtimeIds[1])

        P3AudioCatalogRepository.parseCatalog(catalog, runtimeIds)
    }

    private fun validBaseline(): JSONObject = JSONObject()
        .put("schemaVersion", 1)
        .put("kind", "MIYORARE_AUDIO_CATALOG_BASELINE")
        .put(
            "miyorare",
            JSONObject()
                .put("repository", "Noirero/Miyorare")
                .put("lineageBranch", "beta")
                .put("catalogCommit", miyorareCommit)
                .put("catalogPath", "extensions/miyorare-audio/pack.json")
                .put("validatorPath", "extensions/miyorare-audio/tools/validate_pack.py")
                .put("sourcePullRequest", 219),
        )
        .put(
            "hiraukan",
            JSONObject()
                .put("repository", "Noirero/Hiraukan")
                .put("lineageBranch", "beta")
                .put("runtimeCommit", hiraukanCommit)
                .put("runtimeRegistryPath", "lib/src/extensions/audio_extension_provider.dart"),
        )
        .put("expectedRuntimeIds", JSONArray(runtimeIds))
        .put(
            "deviceValidation",
            JSONObject()
                .put("state", "DEFERRED_BY_OWNER")
                .put("requiredForRelease", false)
                .put("validated", false)
                .put("note", "Owner deferred real-device validation; this is not device evidence."),
        )
        .put(
            "releaseEligibility",
            JSONObject()
                .put("state", "ELIGIBLE")
                .put("miyorareBetaMerged", true)
                .put("reason", "FINAL_MIYORARE_BETA_MERGED"),
        )

    private fun validCatalog(): JSONObject {
        val extensions = JSONArray()
        runtimeIds.forEachIndexed { index, id ->
            extensions.put(
                JSONObject()
                    .put("id", id)
                    .put("name", "Runtime ${index + 1}")
                    .put("version", "1.0.0")
                    .put("type", "audio")
                    .put("auth", if (index == 0) "optional" else "none")
                    .put("languages", JSONArray(listOf("ja")))
                    .put("capabilities", JSONArray(listOf("catalog", "search", "detail")))
                    .put(
                        "delivery",
                        JSONObject()
                            .put("kind", "builtin")
                            .put("runtimeId", id),
                    ),
            )
        }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("packId", "miyorare-audio")
            .put("displayName", "Miyorare Audio")
            .put("mediaType", "audio")
            .put(
                "consumer",
                JSONObject()
                    .put("application", "Hiraukan")
                    .put("repository", "Noirero/Hiraukan")
                    .put("extensionSchemaVersion", 1),
            )
            .put("extensions", extensions)
    }
}
