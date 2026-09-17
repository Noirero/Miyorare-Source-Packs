package com.noirero.miyorare.sourcelab

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class OwnerControlActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceLabPhase1Theme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    OwnerControlScreen()
                }
            }
        }
    }
}

private data class OwnerDashboardUiState(
    val snapshot: LiveFarmSnapshot? = null,
    val control: SourceLabResolvedControlState? = null,
    val initialLoading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
)

private data class OwnerInventoryUiState(
    val snapshot: SourceInventorySnapshot? = null,
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
)

@Composable
private fun OwnerControlScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var dashboard by remember { mutableStateOf(OwnerDashboardUiState()) }
    var inventory by remember { mutableStateOf(OwnerInventoryUiState()) }
    var runningAction by remember { mutableStateOf<SourceLabControlAction?>(null) }
    var confirmation by remember { mutableStateOf<SourceLabControlAction?>(null) }
    var operationMessage by remember { mutableStateOf<String?>(null) }

    suspend fun refreshDashboard() {
        val hadData = dashboard.snapshot != null && dashboard.control != null
        dashboard = dashboard.copy(
            initialLoading = !hadData,
            refreshing = hadData,
            error = null,
        )
        dashboard = try {
            val snapshot = withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
            val control = SourceLabControlClient.resolveState(context, snapshot)
            OwnerDashboardUiState(
                snapshot = snapshot,
                control = control,
                initialLoading = false,
                refreshing = false,
            )
        } catch (error: SourceLabControlException) {
            dashboard.copy(initialLoading = false, refreshing = false, error = error.reason)
        } catch (error: Throwable) {
            dashboard.copy(
                initialLoading = false,
                refreshing = false,
                error = error.message ?: error.javaClass.simpleName,
            )
        }
    }

    suspend fun refreshInventory() {
        val hadData = inventory.snapshot != null
        inventory = inventory.copy(loading = !hadData, refreshing = hadData, error = null)
        val result = runCatching {
            SourceInventoryRepository.loadInventory(context, forceRefresh = true)
        }
        inventory = OwnerInventoryUiState(
            snapshot = result.getOrNull() ?: inventory.snapshot,
            loading = false,
            refreshing = false,
            error = result.exceptionOrNull()?.let { it.message ?: it.javaClass.simpleName },
        )
    }

    LaunchedEffect(Unit) {
        val cached = SourceInventoryCacheReader.load(context)
        if (cached != null) {
            inventory = OwnerInventoryUiState(snapshot = cached, loading = false, refreshing = true)
        }
        launch { refreshDashboard() }
        launch { refreshInventory() }
    }

    fun refreshAll() {
        scope.launch { refreshDashboard() }
        scope.launch { refreshInventory() }
    }

    fun runAction(action: SourceLabControlAction, snapshot: LiveFarmSnapshot) {
        scope.launch {
            runningAction = action
            operationMessage = null
            try {
                if (action == SourceLabControlAction.APPROVE) {
                    val result = SourceLabControlClient.approveAndPublish(context, snapshot)
                    operationMessage =
                        "Approve → Promote → Sign → Publish succeeded · runs " +
                            "${result.approvalRunId}/${result.promotionRunId}/${result.signingRunId}/${result.publishRunId}"
                } else {
                    val result = SourceLabControlClient.execute(context, snapshot, action)
                    operationMessage = "${action.name.replace('_', ' ')} succeeded · run ${result.runId}"
                }
                refreshAll()
            } catch (error: SourceLabControlException) {
                operationMessage = "${action.name.replace('_', ' ')} · ${error.reason}"
                refreshAll()
            } catch (error: Throwable) {
                operationMessage = "${action.name.replace('_', ' ')} · ${error.message ?: error.javaClass.simpleName}"
                refreshAll()
            } finally {
                runningAction = null
            }
        }
    }

    val snapshot = dashboard.snapshot
    val control = dashboard.control
    val ready = snapshot != null && control != null

    if (confirmation != null && snapshot != null && control != null) {
        val action = confirmation!!
        AlertDialog(
            onDismissRequest = { if (runningAction == null) confirmation = null },
            title = {
                Text(
                    if (action == SourceLabControlAction.APPROVE) "Confirm Approve & Auto Publish"
                    else "Confirm ${action.name.replace('_', ' ')}",
                    fontWeight = FontWeight.Bold,
                )
            },
            text = {
                Text(
                    confirmationText(action, snapshot, control),
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                )
            },
            confirmButton = {
                Button(
                    enabled = runningAction == null,
                    onClick = {
                        confirmation = null
                        runAction(action, snapshot)
                    },
                ) {
                    Text(if (action == SourceLabControlAction.APPROVE) "Approve & Auto Publish" else "Confirm")
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmation = null }) { Text("Cancel") }
            },
        )
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "header") {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Miyorare Source Lab", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                    Text(
                        "Compatibility Farm Control Panel",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
                TextButton(
                    onClick = { context.startActivity(Intent(context, SourceLabDiagnosticsActivity::class.java)) },
                ) { Text("Diagnostics") }
            }
        }

        item(key = "owner") {
            OwnerStatusCard(
                state = dashboard,
                ready = ready,
                onRefresh = ::refreshAll,
            )
        }

        operationMessage?.let { message ->
            item(key = "operation") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Text(message, Modifier.fillMaxWidth().padding(14.dp), fontWeight = FontWeight.SemiBold)
                }
            }
        }

        if (snapshot != null && control != null) {
            item(key = "farm-status") {
                FarmStatusCard(
                    snapshot = snapshot,
                    availability = control.actions.getValue(SourceLabControlAction.RUN_FARM),
                    running = runningAction == SourceLabControlAction.RUN_FARM,
                    onRun = { runAction(SourceLabControlAction.RUN_FARM, snapshot) },
                )
            }

            item(key = "overview") {
                SourceOverviewCard(
                    snapshot = snapshot,
                    inventory = inventory,
                    onOpenSources = { context.startActivity(Intent(context, SourceInventoryActivity::class.java)) },
                )
            }

            item(key = "recent") { RecentActivityCard(snapshot.recentRuns) }

            item(key = "approval") {
                PendingApprovalCard(
                    snapshot = snapshot,
                    availability = control.actions.getValue(SourceLabControlAction.APPROVE),
                    running = runningAction == SourceLabControlAction.APPROVE,
                    onApprove = { confirmation = SourceLabControlAction.APPROVE },
                )
            }

            val recoveryActions = listOf(
                SourceLabControlAction.PROMOTE,
                SourceLabControlAction.SIGN,
                SourceLabControlAction.PUBLISH,
            ).filter { control.actions.getValue(it).available }
            if (recoveryActions.isNotEmpty()) {
                item(key = "recovery-title") {
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("Recovery actions", fontWeight = FontWeight.Bold)
                        Text(
                            "Only shown when the backend exposes a valid recovery capability.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                items(recoveryActions, key = { "recovery-${it.name}" }) { action ->
                    RecoveryActionCard(
                        availability = control.actions.getValue(action),
                        running = runningAction == action,
                        onClick = { confirmation = action },
                    )
                }
            }
        }

        item(key = "security-note") {
            Text(
                "Owner actions remain fail-closed. Repository writes, promotion, signing and publishing are performed by GitHub Actions; the APK does not store repository write tokens or signing material.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun OwnerStatusCard(
    state: OwnerDashboardUiState,
    ready: Boolean,
    onRefresh: () -> Unit,
) {
    val container = if (ready) Color(0xFF103328) else MaterialTheme.colorScheme.surfaceVariant
    Card(colors = CardDefaults.cardColors(containerColor = container)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text(
                        if (ready) "OWNER · AUTHORIZED" else "OWNER · VERIFYING",
                        color = if (ready) SourceLabGood else MaterialTheme.colorScheme.onSurface,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        if (ready) "GitHub identity and backend authorization verified"
                        else "Validating Owner session and backend capability",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                when {
                    state.refreshing || state.initialLoading -> CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                    ready -> SourceLabStatusBadge("Live", SourceLabTone.GOOD)
                }
            }
            state.error?.let { error ->
                Text("Control refresh: $error", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            OutlinedButton(onClick = onRefresh, enabled = !state.refreshing && !state.initialLoading) {
                Text(if (ready) "Refresh state" else "Retry authorization")
            }
        }
    }
}

@Composable
private fun FarmStatusCard(
    snapshot: LiveFarmSnapshot,
    availability: SourceLabActionAvailability,
    running: Boolean,
    onRun: () -> Unit,
) {
    val stateLabel = when {
        snapshot.approvalCandidate != null -> "Pending approval"
        snapshot.lastPromotion != null && snapshot.lastPublish?.candidateSetId != snapshot.lastPromotion.candidateSetId -> "Promotion pending"
        else -> "Ready for Farm"
    }
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Farm Status", fontWeight = FontWeight.Bold)
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text(stateLabel, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text(
                        "${snapshot.sources.size} sources in Farm",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                SourceLabStatusBadge(
                    if (availability.available) "Available" else "Locked",
                    if (availability.available) SourceLabTone.GOOD else SourceLabTone.NEUTRAL,
                )
            }
            Button(
                onClick = onRun,
                enabled = availability.available && !running,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (running) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.size(8.dp))
                    Text("Running Farm")
                } else {
                    Text("Run Compatibility Farm")
                }
            }
            if (!availability.available) {
                Text(
                    availability.reason,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun SourceOverviewCard(
    snapshot: LiveFarmSnapshot,
    inventory: OwnerInventoryUiState,
    onOpenSources: () -> Unit,
) {
    val sourceInventory = inventory.snapshot
    val summary = sourceInventory?.summary(snapshot.sources.map { it.canonicalId }.toSet())
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Source Overview", fontWeight = FontWeight.Bold)
                if (inventory.refreshing || inventory.loading) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OverviewMetric("All Sources", summary?.allSources?.toString() ?: "—", Modifier.weight(1f))
                OverviewMetric("In Farm", snapshot.sources.size.toString(), Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OverviewMetric("Needs Attention", summary?.needsAttention?.toString() ?: "—", Modifier.weight(1f))
                OverviewMetric("Candidate", if (snapshot.approvalCandidate != null) "1" else "0", Modifier.weight(1f))
            }
            inventory.error?.let {
                Text("Inventory refresh unavailable; cached data is retained.", color = SourceLabWarning, style = MaterialTheme.typography.bodySmall)
            }
            Button(onClick = onOpenSources, modifier = Modifier.fillMaxWidth()) { Text("Open Sources") }
        }
    }
}

@Composable
private fun OverviewMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(12.dp), color = SourceLabSurface) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun RecentActivityCard(runs: List<LiveFarmRun>) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Recent Activity", fontWeight = FontWeight.Bold)
            if (runs.isEmpty()) {
                Text("No recent Farm runs available.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                runs.take(4).forEach { run ->
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Surface(shape = RoundedCornerShape(10.dp), color = SourceLabPrimaryStrong) {
                            Text("F", Modifier.padding(horizontal = 10.dp, vertical = 7.dp), fontWeight = FontWeight.Bold)
                        }
                        Column(Modifier.weight(1f)) {
                            Text(run.title, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold)
                            Text(
                                "Run #${run.runNumber}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        val conclusion = run.conclusion?.uppercase() ?: run.status.uppercase()
                        val tone = when (conclusion) {
                            "SUCCESS" -> SourceLabTone.GOOD
                            "FAILURE", "CANCELLED" -> SourceLabTone.ERROR
                            "IN_PROGRESS", "QUEUED" -> SourceLabTone.ACCENT
                            else -> SourceLabTone.NEUTRAL
                        }
                        SourceLabStatusBadge(conclusion.replace('_', ' '), tone)
                    }
                }
            }
        }
    }
}

@Composable
private fun PendingApprovalCard(
    snapshot: LiveFarmSnapshot,
    availability: SourceLabActionAvailability,
    running: Boolean,
    onApprove: () -> Unit,
) {
    val candidate = snapshot.approvalCandidate
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Pending Approval", fontWeight = FontWeight.Bold)
                SourceLabStatusBadge(
                    if (candidate == null) "None" else candidate.state.replace('_', ' '),
                    if (candidate?.publishEligible == true) SourceLabTone.GOOD else SourceLabTone.NEUTRAL,
                )
            }
            if (candidate == null) {
                Text("No candidate is waiting. Run Farm will evaluate live upstream state.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                Text("Candidate is ready for Owner review.")
                Button(
                    onClick = onApprove,
                    enabled = availability.available && !running,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (running) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    else Text("Approve & Auto Publish")
                }
                if (!availability.available) {
                    Text(availability.reason, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun RecoveryActionCard(
    availability: SourceLabActionAvailability,
    running: Boolean,
    onClick: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Row(
            Modifier.fillMaxWidth().padding(14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(availability.action.name.replace('_', ' '), fontWeight = FontWeight.Bold)
                Text(availability.reason, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            OutlinedButton(onClick = onClick, enabled = availability.available && !running) {
                if (running) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                else Text("Open")
            }
        }
    }
}

private fun confirmationText(
    action: SourceLabControlAction,
    snapshot: LiveFarmSnapshot,
    control: SourceLabResolvedControlState,
): String {
    val candidate = snapshot.approvalCandidate
    val promotion = snapshot.lastPromotion
    val lines = mutableListOf<String>()
    lines += "ACTION: ${action.name}"
    lines += "BRANCH: ${snapshot.branch}"
    if (candidate != null) {
        lines += "candidateSetId: ${candidate.candidateSetId}"
        candidate.providers.forEach { (provider, item) ->
            lines += "$provider current=${item.current}"
            lines += "$provider candidate=${item.candidate}"
        }
        lines += "farmEvidence=${candidate.evidenceBinding.farmEvidenceSha256}"
        lines += "gate=${candidate.evidenceBinding.gateSha256}"
        lines += "repair=${candidate.evidenceBinding.repairEvidenceSha256}"
    } else if (promotion != null) {
        lines += "candidateSetId: ${promotion.candidateSetId}"
        promotion.providers.forEach { (provider, commit) -> lines += "$provider=$commit" }
        lines += "promotionRunId=${promotion.promotionRunId}"
    }
    when (action) {
        SourceLabControlAction.APPROVE -> {
            lines += "One confirmation starts APPROVE → PROMOTE → SIGN → PUBLISH."
            lines += "Each stage reloads live state and revalidates its exact prerequisite."
        }
        SourceLabControlAction.PROMOTE -> lines += "approvalRunId=${control.approvalRunId ?: "MISSING"}"
        SourceLabControlAction.SIGN -> lines += "Signing: GitHub Artifact Attestation only"
        SourceLabControlAction.PUBLISH -> {
            lines += "signingRunId=${control.signingRunId ?: "MISSING"}"
            lines += "This creates an official immutable Source Pack GitHub release."
        }
        else -> Unit
    }
    lines += "Server revalidates every SHA/evidence/run before mutation."
    return lines.joinToString("\n")
}
