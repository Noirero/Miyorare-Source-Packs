package com.noirero.miyorare.sourcelab

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DashboardConsistencyTest {
    private fun source(path: String): String = File("src/main/java/com/noirero/miyorare/sourcelab/$path").readText()

    @Test
    fun liveDashboardSnapshotRequiresPendingWorkerAuthority() {
        val repository = source("SourceLabRepository.kt")

        assertTrue(repository.contains("val pendingWorkerJob = async(Dispatchers.IO)"))
        assertTrue(repository.contains("loadPendingWorkerState(farmCommit)"))
        assertFalse(repository.contains("runCatching { loadPendingWorkerState(farmCommit) }.getOrNull()"))
    }

    @Test
    fun recentWorkflowHistoryRemainsNonAuthoritativeBestEffort() {
        val repository = source("SourceLabRepository.kt")

        assertTrue(repository.contains("runCatching { loadRecentFarmRuns() }.getOrDefault(emptyList())"))
    }

    @Test
    fun ownerQueueMetricsComeFromPendingWorkerState() {
        val ownerDashboard = source("AutonomousOwnerControlActivity.kt")

        assertTrue(ownerDashboard.contains("pending?.readyCount"))
        assertTrue(ownerDashboard.contains("pending?.needsAttentionCount"))
        assertTrue(ownerDashboard.contains("pending?.retryCount"))
        assertTrue(ownerDashboard.contains("pending?.approvedCount"))
    }

    @Test
    fun viewerCheckpointMetricsRemainExplicitlySeparatedFromLiveRuntimeState() {
        val viewer = source("LocalizedMainActivity.kt")

        assertTrue(viewer.contains("Embedded checkpoint evidence is shown separately from live runtime state."))
        assertTrue(viewer.contains("supporting = \"verified checkpoint\""))
        assertTrue(viewer.contains("supporting = \"checkpoint\""))
    }
}
