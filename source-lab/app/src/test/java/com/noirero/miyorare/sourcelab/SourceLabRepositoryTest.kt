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
}
