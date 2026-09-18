package com.noirero.miyorare.sourcelab

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PendingWorkerStateTest {
    @Test
    fun parsesSchemaV2QueueSummary() {
        val root = JSONObject(
            """
            {
              "schemaVersion": 2,
              "updatedAt": "2026-09-18T02:00:00Z",
              "sources": {
                "ready-b": {"state": "READY_FOR_APPROVAL"},
                "retry": {"state": "RETRY"},
                "held": {"state": "NEEDS_ATTENTION"},
                "approved": {"state": "APPROVED"},
                "parser": {"state": "PARSER_PENDING"},
                "ready-a": {"state": "READY_FOR_APPROVAL"}
              }
            }
            """.trimIndent(),
        )

        val parsed = SourceLabRepository.parsePendingWorkerState(root)

        assertEquals(2, parsed.schemaVersion)
        assertEquals(2, parsed.readyCount)
        assertEquals(2, parsed.retryCount)
        assertEquals(1, parsed.needsAttentionCount)
        assertEquals(1, parsed.approvedCount)
        assertEquals(listOf("ready-a", "ready-b"), parsed.readyCanonicalIds)
        assertEquals("2026-09-18T02:00:00Z", parsed.updatedAt)
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsLegacyWorkerState() {
        SourceLabRepository.parsePendingWorkerState(
            JSONObject("""{"schemaVersion":1,"sources":{}}"""),
        )
    }

    @Test
    fun missingUpdatedAtIsAllowed() {
        val parsed = SourceLabRepository.parsePendingWorkerState(
            JSONObject("""{"schemaVersion":2,"sources":{}}"""),
        )
        assertNull(parsed.updatedAt)
    }
}
