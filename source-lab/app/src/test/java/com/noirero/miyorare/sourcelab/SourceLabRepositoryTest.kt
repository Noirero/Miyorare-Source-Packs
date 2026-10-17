package com.noirero.miyorare.sourcelab

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class SourceLabRepositoryTest {
    @Test
    fun parsesExactFarmBranchHead() {
        val sha = "a".repeat(40)
        val parsed = SourceLabRepository.parseFarmBranchHead(
            JSONObject("""{"commit":{"sha":"$sha"}}"""),
        )

        assertEquals(sha, parsed)
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsInvalidFarmBranchHead() {
        SourceLabRepository.parseFarmBranchHead(
            JSONObject("""{"commit":{"sha":"compatibility-farm-foundation"}}"""),
        )
    }

    @Test
    fun farmAuthorityUrlsArePinnedToExactCommit() {
        val sha = "b".repeat(40)
        val registry = SourceLabRepository.farmRawUrl(sha, "compatibility/source-registry.json")
        val status = SourceLabRepository.farmRawUrl(sha, "upstream/status.json")
        val worker = SourceLabRepository.farmRawUrl(sha, "automation/pending-worker-state.json")

        assertEquals(
            "https://raw.githubusercontent.com/Noirero/Miyorare-Source-Packs/$sha/compatibility/source-registry.json",
            registry,
        )
        assertEquals(
            "https://raw.githubusercontent.com/Noirero/Miyorare-Source-Packs/$sha/upstream/status.json",
            status,
        )
        assertEquals(
            "https://raw.githubusercontent.com/Noirero/Miyorare-Source-Packs/$sha/automation/pending-worker-state.json",
            worker,
        )
        assertFalse(registry.contains("/${SourceLabRepository.farmBranch}/"))
        assertFalse(status.contains("/${SourceLabRepository.farmBranch}/"))
        assertFalse(worker.contains("/${SourceLabRepository.farmBranch}/"))
    }

    @Test
    fun providerHealthAndReleaseEligibilityRemainIndependent() {
        val current = "c".repeat(40)
        val status = JSONObject(
            """
            {
              "providers": {
                "uma": {
                  "updateState": "PROMOTED",
                  "runtimeHealth": "DEGRADED",
                  "activeCommit": "$current",
                  "lastKnownGood": "$current",
                  "recoveryState": "IDLE",
                  "reason": "owner-approved-exact-promotion",
                  "releaseEligibility": "ELIGIBLE",
                  "releaseEligibilityReason": "ACTIVE_COMMIT_IS_LAST_KNOWN_GOOD"
                }
              }
            }
            """.trimIndent(),
        )

        val provider = SourceLabRepository.parseProviderStates(status).single()

        assertEquals("DEGRADED", provider.runtimeHealth)
        assertEquals("ELIGIBLE", provider.releaseEligibility)
        assertEquals("ACTIVE_COMMIT_IS_LAST_KNOWN_GOOD", provider.releaseEligibilityReason)
        assertEquals(current, provider.activeCommit)
        assertEquals(current, provider.lastKnownGood)
    }

    @Test
    fun approvalCandidatePreservesLockedRefsAndScopedSources() {
        val current = "d".repeat(40)
        val locked = "e".repeat(40)
        val candidate = SourceLabRepository.parseApprovalCandidate(
            JSONObject(
                """
                {
                  "candidateSetId": "${"f".repeat(64)}",
                  "state": "WAITING_FOR_APPROVAL",
                  "gateFingerprint": "gate-fingerprint",
                  "providers": {
                    "keiyoushi": {"current": "$current", "candidate": "$locked"}
                  },
                  "evidenceBinding": {
                    "farmEvidenceSha256": "farm",
                    "gateSha256": "gate",
                    "repairEvidenceSha256": "repair",
                    "repairEvidenceCount": 0
                  },
                  "publishEligible": false,
                  "sourceScope": {
                    "keiyoushi": [
                      "miyorare:miyorare-en:AQUAMANGA",
                      "miyorare:miyorare-id:BACAMI"
                    ]
                  }
                }
                """.trimIndent(),
            ),
        )

        assertEquals(current, candidate.providers.getValue("keiyoushi").current)
        assertEquals(locked, candidate.providers.getValue("keiyoushi").candidate)
        assertEquals(
            listOf("miyorare:miyorare-en:AQUAMANGA", "miyorare:miyorare-id:BACAMI"),
            candidate.sourceScope.getValue("keiyoushi"),
        )
    }

    @Test
    fun promotionPreservesScopedSources() {
        val promoted = "1".repeat(40)
        val promotion = SourceLabRepository.parsePromotionState(
            JSONObject(
                """
                {
                  "candidateSetId": "${"2".repeat(64)}",
                  "promotionRunId": 77,
                  "providers": {"keiyoushi": "$promoted"},
                  "publishEligible": false,
                  "sourceScope": {
                    "keiyoushi": ["miyorare:miyorare-id:KIRYUU"]
                  }
                }
                """.trimIndent(),
            ),
        )

        assertEquals(promoted, promotion.providers.getValue("keiyoushi"))
        assertEquals(listOf("miyorare:miyorare-id:KIRYUU"), promotion.sourceScope.getValue("keiyoushi"))
    }
}
