package com.noirero.miyorare.sourcelab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SourceInventoryRepositoryTest {
    @Test
    fun parsesProviderSpecificMappingsWithoutInventingUniversalIds() {
        val snapshot = SourceInventoryRepository.parseInventory(
            """
            {
              "schemaVersion": 1,
              "kind": "MIYORARE_SOURCE_INVENTORY",
              "informationalOnly": true,
              "providerSnapshots": {
                "keiyoushi": {"commit": "${"a".repeat(40)}"},
                "uma": {"commit": "${"b".repeat(40)}"}
              },
              "sources": [
                {
                  "canonicalId": "miyorare:miyorare-id:KOMIKU",
                  "displayName": "Komiku",
                  "language": "id",
                  "identityConfidence": "explicit",
                  "needsAttention": false,
                  "attentionReasons": [],
                  "providers": {
                    "keiyoushi": {
                      "available": true,
                      "sourceId": 4838485846640015979,
                      "sourceName": "Komiku",
                      "module": "src/id/komiku"
                    },
                    "uma": {
                      "available": true,
                      "sourceName": "KOMIKU",
                      "displayName": "Komiku",
                      "file": "src/main/kotlin/tsuki/site/id/Komiku.kt"
                    }
                  }
                }
              ]
            }
            """.trimIndent(),
            branchCommit = "c".repeat(40),
        )

        assertEquals(1, snapshot.sources.size)
        assertEquals("c".repeat(40), snapshot.branchCommit)
        val source = snapshot.sources.single()
        assertEquals("miyorare:miyorare-id:KOMIKU", source.canonicalId)
        assertEquals(4838485846640015979L, source.providers.getValue("keiyoushi").sourceId)
        assertEquals(null, source.providers.getValue("uma").sourceId)
        assertEquals("src/main/kotlin/tsuki/site/id/Komiku.kt", source.providers.getValue("uma").file)
        assertFalse(source.needsAttention)
    }

    @Test
    fun summaryKeepsInventorySeparateFromFarmMembership() {
        val snapshot = SourceInventorySnapshot(
            sources = listOf(
                InventorySource(
                    "miyorare:x:A",
                    "A",
                    "ID",
                    "explicit",
                    false,
                    emptyList(),
                    mapOf("uma" to mapping("uma")),
                ),
                InventorySource(
                    "miyorare:x:B",
                    "B",
                    "EN",
                    "exact-name",
                    true,
                    listOf("ambiguous"),
                    mapOf("gekkoushi" to mapping("gekkoushi")),
                ),
            ),
            providerCommits = emptyMap(),
            branch = SourceInventoryRepository.inventoryBranch,
            branchCommit = "d".repeat(40),
            retrievedAtEpochMs = 0L,
        )

        val summary = snapshot.summary(setOf("miyorare:x:A"))
        assertEquals(2, summary.allSources)
        assertEquals(1, summary.inFarm)
        assertEquals(1, summary.notEnrolled)
        assertEquals(1, summary.needsAttention)
        assertTrue(snapshot.sources[1].needsAttention)
    }

    @Test
    fun allLanguageDoesNotDuplicateAllFilterSentinel() {
        val filters = sourceInventoryLanguageFilters(
            listOf(
                InventorySource(
                    "miyorare:x:GLOBAL",
                    "Global",
                    "ALL",
                    "exact-name",
                    false,
                    emptyList(),
                    mapOf("gekkoushi" to mapping("gekkoushi")),
                ),
                InventorySource(
                    "miyorare:x:ID",
                    "Indonesia",
                    "ID",
                    "exact-name",
                    false,
                    emptyList(),
                    mapOf("uma" to mapping("uma")),
                ),
            ),
        )

        assertEquals(1, filters.count { it == "ALL" })
        assertEquals(listOf("ALL", "ID"), filters)
    }

    @Test
    fun parsesFarmMembershipDetailsSeparatelyFromInventory() {
        val farm = SourceInventoryRepository.parseFarmRegistry(
            """
            {
              "schemaVersion": 1,
              "scope": {
                "languages": ["id", "en"]
              },
              "defaults": {
                "updateState": "PROMOTED",
                "runtimeHealth": "UNKNOWN",
                "approvalState": "NOT_READY",
                "ownerActionRequired": false,
                "repairPolicy": {
                  "autoDiagnose": true,
                  "safeSelfRepair": true,
                  "keepLastKnownGood": true,
                  "validatedCanonicalFallback": true
                }
              },
              "sources": [
                {
                  "canonicalId": "miyorare:miyorare-id:KOMIKU",
                  "contentProfile": "manga",
                  "authType": "NO_AUTH",
                  "adapterFamily": "reader",
                  "currentVersion": {"uma": "${"a".repeat(40)}"},
                  "lastKnownGood": {"uma": "${"b".repeat(40)}"}
                }
              ]
            }
            """.trimIndent(),
            branchCommit = "e".repeat(40),
        )
        val source = farm.sources.single()
        assertEquals("e".repeat(40), farm.branchCommit)
        assertEquals(setOf("id", "en"), farm.languages)
        assertEquals("PROMOTED", source.updateState)
        assertEquals("UNKNOWN", source.runtimeHealth)
        assertEquals("a".repeat(40), source.currentVersion.getValue("uma"))
        assertTrue(source.repairPolicy!!.safeSelfRepair)
        assertFalse(source.ownerActionRequired)
    }

    private fun mapping(provider: String) = InventoryProviderMapping(
        provider = provider,
        available = true,
        sourceName = "SOURCE",
        displayName = null,
        sourceId = null,
        module = null,
        file = "source.kt",
        baseUrl = null,
        extensionVersionCode = null,
    )
}
