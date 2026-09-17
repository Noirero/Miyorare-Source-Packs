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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class AutonomousOwnerControlActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceLabPhase1Theme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    AutonomousOwnerDashboard()
                }
            }
        }
    }
}

private data class AutonomousDashboardState(
    val snapshot: LiveFarmSnapshot? = null,
    val control: SourceLabResolvedControlState? = null,
    val initialLoading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
)

private enum class RoutineFarmState {
    ALL_GOOD,
    APPROVAL_REQUIRED,
    PUBLISHING,
    HELD,
    INFRASTRUCTURE_FAILURE,
}

@Composable
private fun AutonomousOwnerDashboard() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf(AutonomousDashboardState()) }
    var approving by remember { mutableStateOf(false) }
    var confirmApproval by remember { mutableStateOf(false) }
    var operation by remember { mutableStateOf<String?>(null) }

    suspend fun refresh() {
        val hasData = state.snapshot != null
        state = state.copy(
            control = null,
            initialLoading = !hasData,
            refreshing = hasData,
            error = null,
        )
        state = try {
            val snapshot = withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
            val control = SourceLabControlClient.resolveState(context, snapshot)
            AutonomousDashboardState(snapshot = snapshot, control = control)
        } catch (error: SourceLabControlException) {
            state.copy(
                control = null,
                initialLoading = false,
                refreshing = false,
                error = error.reason,
            )
        } catch (error: Throwable) {
            state.copy(
                control = null,
                initialLoading = false,
                refreshing = false,
                error = error.message ?: error.javaClass.simpleName,
            )
        }
    }

    fun approveAndAutoPublish(snapshot: LiveFarmSnapshot) {
        scope.launch {
            approving = true
            operation = null
            try {
                val result = SourceLabControlClient.approveAndPublish(context, snapshot)
                operation = "Published successfully · ${result.approvalRunId}/${result.promotionRunId}/${result.signingRunId}/${result.publishRunId}"
            } catch (error: SourceLabControlException) {
                operation = "Approval pipeline stopped safely · ${error.reason}"
            } catch (error: Throwable) {
                operation = "Approval pipeline stopped safely · ${error.message ?: error.javaClass.simpleName}"
            } finally {
                approving = false
                refresh()
            }
        }
    }

    LaunchedEffect(Unit) { refresh() }

    val snapshot = state.snapshot
    val control = state.control
    val approvalAvailability = control?.actions?.get(SourceLabControlAction.APPROVE)
    val routineState = snapshot?.let(::resolveRoutineFarmState)

    if (confirmApproval && snapshot?.approvalCandidate != null && approvalAvailability != null) {
        val candidate = snapshot.approvalCandidate
        AlertDialog(
            onDismissRequest = { if (!approving) confirmApproval = false },
            title = { Text("Approve & Auto Publish", fontWeight = FontWeight.Bold) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        "This is the only routine Owner mutation. The backend will revalidate the exact candidate and then run Approve → Promote → Sign → Publish.",
                    )
                    Text(candidate.candidateSetId, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
                    candidate.providers.forEach { (provider, refs) ->
                        Text(
                            "${provider.uppercase()}: ${refs.current.take(10)} → ${refs.candidate.take(10)}",
                            fontFamily = FontFamily.Monospace,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            },
            confirmButton = {
                Button(
                    enabled = approvalAvailability.available && !approving,
                    onClick = {
                        confirmApproval = false
                        approveAndAutoPublish(snapshot)
                    },
                ) { Text("Approve & Auto Publish") }
            },
            dismissButton = {
                TextButton(onClick = { confirmApproval = false }) { Text("Cancel") }
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
                        "Autonomous Compatibility Farm",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                TextButton(
                    onClick = { context.startActivity(Intent(context, SettingsActivity::class.java)) },
                ) { Text("Settings") }
            }
        }

        if (state.initialLoading && snapshot == null) {
            item(key = "loading") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Row(
                        Modifier.fillMaxWidth().padding(18.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                        Column {
                            Text("Checking Farm state", fontWeight = FontWeight.Bold)
                            Text(
                                "Reading live automation state and revalidating Owner capability.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }

        if (snapshot != null) {
            item(key = "routine-state") {
                RoutineStateCard(
                    state = routineState ?: RoutineFarmState.INFRASTRUCTURE_FAILURE,
                    snapshot = snapshot,
                    approvalAvailability = approvalAvailability,
                    approving = approving,
                    onReview = { context.startActivity(Intent(context, ApprovalReviewActivity::class.java)) },
                    onApprove = { confirmApproval = true },
                    onExceptions = { context.startActivity(Intent(context, ReportsActivity::class.java)) },
                    onDiagnostics = { context.startActivity(Intent(context, SourceLabDiagnosticsActivity::class.java)) },
                )
            }
        }

        operation?.let { message ->
            item(key = "operation") {
                Card(colors = CardDefaults.cardColors(containerColor = SourceLabSurface)) {
                    Text(message, Modifier.fillMaxWidth().padding(14.dp), fontWeight = FontWeight.SemiBold)
                }
            }
        }

        state.error?.let { error ->
            item(key = "control-error") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        SourceLabStatusBadge("INFRASTRUCTURE FAILURE", SourceLabTone.ERROR)
                        Text("Owner control verification failed. No mutation is available.", fontWeight = FontWeight.Bold)
                        Text(error, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }

        item(key = "navigation") {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Text("Explore", fontWeight = FontWeight.Bold)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = { context.startActivity(Intent(context, SourceInventoryActivity::class.java)) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Sources") }
                        OutlinedButton(
                            onClick = { context.startActivity(Intent(context, ReportsActivity::class.java)) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Reports") }
                    }
                }
            }
        }

        if (snapshot != null && control != null) {
            val recoveryActions = listOf(
                SourceLabControlAction.PROMOTE,
                SourceLabControlAction.SIGN,
                SourceLabControlAction.PUBLISH,
            ).filter { control.actions.getValue(it).available }
            if (recoveryActions.isNotEmpty()) {
                item(key = "recovery") {
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            SourceLabStatusBadge("RECOVERY", SourceLabTone.ERROR)
                            Text("Approval pipeline requires recovery", fontWeight = FontWeight.Bold)
                            Text(
                                "Routine automation is paused. Open the advanced recovery dashboard for the exact fail-closed recovery action.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            OutlinedButton(
                                onClick = { context.startActivity(Intent(context, OwnerControlActivity::class.java)) },
                                modifier = Modifier.fillMaxWidth(),
                            ) { Text("Open Recovery Dashboard") }
                        }
                    }
                }
            }
        }

        item(key = "refresh") {
            OutlinedButton(
                onClick = { scope.launch { refresh() } },
                enabled = !state.initialLoading && !state.refreshing && !approving,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (state.refreshing) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.size(8.dp))
                    Text("Refreshing")
                } else {
                    Text("Refresh state")
                }
            }
        }

        item(key = "boundary") {
            Text(
                "Upstream detection and Candidate Farm execution are automatic. Failed or HELD candidates never advance last-known-good. Human approval remains the only routine mutation boundary.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun RoutineStateCard(
    state: RoutineFarmState,
    snapshot: LiveFarmSnapshot,
    approvalAvailability: SourceLabActionAvailability?,
    approving: Boolean,
    onReview: () -> Unit,
    onApprove: () -> Unit,
    onExceptions: () -> Unit,
    onDiagnostics: () -> Unit,
) {
    val candidate = snapshot.approvalCandidate
    val presentation = when (state) {
        RoutineFarmState.ALL_GOOD -> Triple("All good", "No action required. Upstream monitoring and Farm checks run automatically.", SourceLabTone.GOOD)
        RoutineFarmState.APPROVAL_REQUIRED -> Triple("1 update ready", "Candidate passed the safety gates and is waiting for your decision.", SourceLabTone.WARNING)
        RoutineFarmState.PUBLISHING -> Triple("Publishing approved update", "No action required. The approved pipeline is finishing automatically.", SourceLabTone.ACCENT)
        RoutineFarmState.HELD -> Triple("Held / safely blocked", "The bot could not safely advance this candidate. Last-known-good remains active.", SourceLabTone.WARNING)
        RoutineFarmState.INFRASTRUCTURE_FAILURE -> Triple("Infrastructure failure", "Automation needs attention. Last-known-good remains the safe active baseline.", SourceLabTone.ERROR)
    }

    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(presentation.first, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text(presentation.second, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                SourceLabStatusBadge(
                    when (state) {
                        RoutineFarmState.ALL_GOOD -> "ALL GOOD"
                        RoutineFarmState.APPROVAL_REQUIRED -> "APPROVAL REQUIRED"
                        RoutineFarmState.PUBLISHING -> "PUBLISHING"
                        RoutineFarmState.HELD -> "HELD"
                        RoutineFarmState.INFRASTRUCTURE_FAILURE -> "ATTENTION"
                    },
                    presentation.third,
                )
            }

            snapshot.automation?.let { automation ->
                Text(
                    automation.reason.replace('_', ' '),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            when (state) {
                RoutineFarmState.APPROVAL_REQUIRED -> {
                    if (candidate != null) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = onReview, modifier = Modifier.weight(1f)) { Text("Review") }
                            Button(
                                onClick = onApprove,
                                enabled = approvalAvailability?.available == true && !approving,
                                modifier = Modifier.weight(1f),
                            ) {
                                if (approving) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                                else Text("Approve")
                            }
                        }
                        if (approvalAvailability?.available != true) {
                            Text(
                                "Approval is locked until live Owner/backend capability is revalidated${approvalAvailability?.reason?.let { " · $it" }.orEmpty()}.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    } else {
                        Text(
                            "Automation reports approval readiness, but the exact staged candidate is not readable yet. No Approve action is exposed.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                RoutineFarmState.HELD -> OutlinedButton(onClick = onExceptions, modifier = Modifier.fillMaxWidth()) { Text("Open Exceptions") }
                RoutineFarmState.INFRASTRUCTURE_FAILURE -> OutlinedButton(onClick = onDiagnostics, modifier = Modifier.fillMaxWidth()) { Text("Open Diagnostics") }
                RoutineFarmState.ALL_GOOD, RoutineFarmState.PUBLISHING -> Unit
            }
        }
    }
}

private fun resolveRoutineFarmState(snapshot: LiveFarmSnapshot): RoutineFarmState {
    if (snapshot.approvalCandidate?.state == "WAITING_FOR_APPROVAL") {
        return RoutineFarmState.APPROVAL_REQUIRED
    }
    val promotion = snapshot.lastPromotion
    val publish = snapshot.lastPublish
    if (promotion != null && publish?.candidateSetId != promotion.candidateSetId) {
        return RoutineFarmState.PUBLISHING
    }
    return when (snapshot.automation?.state) {
        "APPROVAL_REQUIRED" -> RoutineFarmState.APPROVAL_REQUIRED
        "PUBLISHING" -> RoutineFarmState.PUBLISHING
        "HELD" -> RoutineFarmState.HELD
        "INFRASTRUCTURE_FAILURE" -> RoutineFarmState.INFRASTRUCTURE_FAILURE
        "ALL_GOOD", null -> RoutineFarmState.ALL_GOOD
        else -> RoutineFarmState.INFRASTRUCTURE_FAILURE
    }
}
