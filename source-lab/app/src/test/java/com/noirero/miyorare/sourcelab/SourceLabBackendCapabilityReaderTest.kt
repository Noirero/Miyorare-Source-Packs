package com.noirero.miyorare.sourcelab

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SourceLabBackendCapabilityReaderTest {
    @Test
    fun readsLegacyAndRecognizedOptionalCapabilities() {
        val metadata = JSONObject()
            .put(
                "capabilities",
                JSONArray(
                    listOf(
                        "RUN_FARM",
                        "APPROVE",
                        "PROMOTE",
                        "SIGN",
                        "PUBLISH",
                    ),
                ),
            )
            .put("optionalCapabilities", JSONArray(listOf("ADD_TO_FARM")))

        val capabilities = SourceLabBackendCapabilityReader.parseCapabilityMetadata(metadata)
        assertEquals(SourceLabControlAction.entries.toSet(), capabilities)
        assertTrue(SourceLabControlAction.ADD_TO_FARM in capabilities)
    }

    @Test
    fun unknownOptionalCapabilityNeverGrantsAnythingOrBreaksClient() {
        val metadata = JSONObject()
            .put("capabilities", JSONArray(listOf("RUN_FARM")))
            .put("optionalCapabilities", JSONArray(listOf("FUTURE_ACTION")))

        val capabilities = SourceLabBackendCapabilityReader.parseCapabilityMetadata(metadata)
        assertEquals(setOf(SourceLabControlAction.RUN_FARM), capabilities)
        assertFalse(SourceLabControlAction.ADD_TO_FARM in capabilities)
    }

    @Test(expected = IllegalStateException::class)
    fun unknownLegacyCapabilityStillFailsClosed() {
        val metadata = JSONObject()
            .put("capabilities", JSONArray(listOf("RUN_FARM", "UNKNOWN_WRITE")))
        SourceLabBackendCapabilityReader.parseCapabilityMetadata(metadata)
    }
}
