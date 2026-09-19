package com.noirero.miyorare.sourcelab

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.runtime.mutableIntStateOf
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
    private val resumeGeneration = mutableIntStateOf(0)
    private var hasResumedOnce = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceLabPhase1Theme {
                SourceLabAppSurface {
                    AutonomousOwnerDashboard(resumeGeneration.intValue)
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (hasResumedOnce) {
            resumeGeneration.intValue += 1
        } else {
            hasResumedOnce = true
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
private fun AutonomousOwnerDashboard(resumeGeneration: Int) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf(AutonomousDashboardState()) }
    var approving by remember { mutableStateOf(false) }
    var confirmApproval by remember { mutableStateOf(false) }
    var approvingReadySources by remember { mutableStateOf(false) }
    var confirmReadySourcesApproval by remember { mutableStateOf(false) }
    var operation by remember { mutableStateOf<String?>(null) }

    suspend fun refresh() {
        val hasData = state.snapshot != null
        state = state.copy(
            control = null,
            initialLoading = !hasData,
            refreshing = hasData,
            error = null,
        )

        val snapshot = try {
            withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
        } catch (error: Throwable) {
            state = state.copy(
                control = null,
                initialLoading = false,
                refreshing = false,
                error = error.message ?: error.javaClass.simpleName,
            )
            return
        }

        // Render the live Farm snapshot immediately. Owner/capability
        // verification continues without keeping the whole dashboard blank.
        state = state.copy(
            snapshot = snapshot,
            initialLoading = false,
            refreshing = true,
            error = null,
        )

        state = try {
            val control = SourceLabControlClient.resolveState(context, snapshot)
            state.copy(control = control, initialLoading = false, refreshing = false, error = null)
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

    fun approveReadySources(snapshot: LiveFarmSnapshot) {
        scope.launch {
            approvingReadySources = true
            operation = null
            try {
                val count = snapshot.pendingWorker?.readyCount ?: 0
                val result = SourceLabControlClient.execute(
                    context,
                    snapshot,
                    SourceLabControlAction.APPROVE_READY_SOURCES,
                )
                operation = "Approved $count ready source${if (count == 1) "" else "s"} · run ${result.runId}. Pack sync and release continue automatically."
            } catch (error: SourceLabControlException) {
                operation = "Source approval stopped safely · ${error.reason}"
            } catch (error: Throwable) {
                operation = "Source approval stopped safely · ${error.message ?: error.javaClass.simpleName}"
            } finally {
                approvingReadySources = false
                refresh()
            }
        }
    }

    LaunchedEffect(resumeGeneration) { refresh() }

    val snapshot = state.snapshot
    val control = state.control
    val approvalAvailability = control?.actions?.get(SourceLabControlAction.APPROVE)
    val publishRecoveryAvailability = control?.actions?.get(SourceLabControlAction.PUBLISH)
    val readySourcesApprovalAvailability = control?.actions?.get(SourceLabControlAction.APPROVE_READY_SOURCES)
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

    if (
        confirmReadySourcesApproval &&
        snapshot?.pendingWorker?.readyCount?.let { it > 0 } == true &&
        readySourcesApprovalAvailability != null
    ) {
        val pending = snapshot.pendingWorker
        AlertDialog(
            onDismissRequest = {
                if (!approvingReadySources) confirmReadySourcesApproval = false
            },
            title = { Text("Approve Ready Sources", fontWeight = FontWeight.Bold) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        "${pending.readyCount} source${if (pending.readyCount == 1) "" else "s"} passed schema-v2 real-parser evidence and are waiting for your approval.",
                    )
                    Text(
                        "The backend will revalidate evidence digests and exact provider SHAs before activating anything. Pack sync, build, and release continue automatically afterward.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    pending.readyCanonicalIds.take(5).forEach { canonicalId ->
                        Text(
                            canonicalId,
                            fontFamily = FontFamily.Monospace,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    if (pending.readyCanonicalIds.size > 5) {
                        Text(
                            "+ ${pending.readyCanonicalIds.size - 5} more",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            },
            confirmButton = {
                Button(
                    enabled = readySourcesApprovalAvailability.available && !approvingReadySources,
                    onClick = {
                        confirmReadySourcesApproval = false
                        approveReadySources(snapshot)
                    },
                ) { Text("Approve ${pending.readyCount}") }
            },
            dismissButton = {
                TextButton(onClick = { confirmReadySourcesApproval = false }) { Text("Cancel") }
            },
        )
    }

    Box(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 16.dp, top = 16.dp, end = 16.dp, bottom = 96.dp),
            verticalArrangement = Arrangement.spacedBy(11.dp),
        ) {
            item(key = "header") {
                SourceLabTopBar(
                    title = "Miyorare Source Lab",
                    subtitle = "Compatibility Farm",
                    trailing = {
                        SourceLabStatusBadge(
                            when {
                                control != null -> "OWNER"
                                snapshot != null && state.refreshing -> "VERIFYING"
                                snapshot != null -> "LIVE"
                                else -> "READING"
                            },
                            when {
                                control != null -> SourceLabTone.GOOD
                                snapshot != null && state.refreshing -> SourceLabTone.ACCENT
                                snapshot != null -> SourceLabTone.NEUTRAL
                                else -> SourceLabTone.ACCENT
                            },
                        )
                    },
                )
            }

            if (state.initialLoading && snapshot == null) {
                item(key = "loading") {
                    SourceLabCard(tone = SourceLabTone.ACCENT) {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp, color = SourceLabPrimary)
                            Column(Modifier.weight(1f)) {
                                Text("Reading Compatibility Farm", fontWeight = FontWeight.Bold)
                                Text(
                                    "Live read-only state appears first; Owner capability resolves separately.",
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
                        publishRecoveryAvailability = publishRecoveryAvailability,
                        approving = approving,
                        onReview = { context.startActivity(Intent(context, ApprovalReviewActivity::class.java)) },
                        onApprove = { confirmApproval = true },
                        onPublishRecovery = { context.startActivity(Intent(context, OwnerControlActivity::class.java)) },
                        onExceptions = { context.startActivity(Intent(context, ReportsActivity::class.java)) },
                        onDiagnostics = { context.startActivity(Intent(context, SourceLabDiagnosticsActivity::class.java)) },
                    )
                }

                item(key = "metrics") {
                    val pending = snapshot.pendingWorker
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            SourceLabMetricCard("In Farm", snapshot.sources.size.toString(), Modifier.weight(1f), SourceLabTone.ACCENT)
                            SourceLabMetricCard("Ready", (pending?.readyCount ?: 0).toString(), Modifier.weight(1f), if ((pending?.readyCount ?: 0) > 0) SourceLabTone.WARNING else SourceLabTone.NEUTRAL)
                            SourceLabMetricCard("Held", (pending?.needsAttentionCount ?: 0).toString(), Modifier.weight(1f), if ((pending?.needsAttentionCount ?: 0) > 0) SourceLabTone.ERROR else SourceLabTone.NEUTRAL)
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            SourceLabMetricCard("Retry", (pending?.retryCount ?: 0).toString(), Modifier.weight(1f))
                            SourceLabMetricCard("Approved", (pending?.approvedCount ?: 0).toString(), Modifier.weight(1f), SourceLabTone.GOOD)
                            SourceLabMetricCard("Candidate", if (snapshot.approvalCandidate != null) "1" else "0", Modifier.weight(1f), if (snapshot.approvalCandidate != null) SourceLabTone.WARNING else SourceLabTone.NEUTRAL)
                        }
                    }
                }

                snapshot.pendingWorker?.let { pending ->
                    item(key = "pending-source-approval") {
                        PendingSourceApprovalCard(
                            pending = pending,
                            availability = readySourcesApprovalAvailability,
                            approving = approvingReadySources,
                            onApprove = { confirmReadySourcesApproval = true },
                        )
                    }
                }

                item(key = "recent-activity") {
                    SourceLabCard {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Row(
                                Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text("Recent Activity", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                                TextButton(onClick = { context.startActivity(Intent(context, ReportsActivity::class.java)) }) {
                                    Text("Full report")
                                }
                            }
                            if (snapshot.recentRuns.isEmpty()) {
                                Text(
                                    "No recent Compatibility Farm runs were returned.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            } else {
                                snapshot.recentRuns.take(4).forEach { run ->
                                    Row(
                                        Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(9.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        Box(Modifier.size(30.dp), contentAlignment = Alignment.Center) {
                                            SourceLabIcon(SourceLabIconKind.TEST, Modifier.size(18.dp), SourceLabPrimarySoft)
                                        }
                                        Column(Modifier.weight(1f)) {
                                            Text(
                                                run.title,
                                                fontWeight = FontWeight.SemiBold,
                                                style = MaterialTheme.typography.bodySmall,
                                                maxLines = 1,
                                            )
                                            Text(
                                                "Run #${run.runNumber}",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            )
                                        }
                                        SourceLabStatusBadge(
                                            (run.conclusion?.takeIf { it.isNotBlank() } ?: run.status).uppercase().replace('_', ' '),
                                            when ((run.conclusion?.takeIf { it.isNotBlank() } ?: run.status).lowercase()) {
                                                "success" -> SourceLabTone.GOOD
                                                "failure", "cancelled", "timed_out" -> SourceLabTone.ERROR
                                                "in_progress", "queued", "waiting", "pending" -> SourceLabTone.ACCENT
                                                else -> SourceLabTone.NEUTRAL
                                            },
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }

            operation?.let { message ->
                item(key = "operation") {
                    SourceLabCard(tone = if ("success" in message.lowercase() || "approved" in message.lowercase()) SourceLabTone.GOOD else SourceLabTone.NEUTRAL) {
                        Text(message, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }

            state.error?.let { error ->
                item(key = "control-error") {
                    SourceLabCard(tone = SourceLabTone.ERROR) {
                        Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                            SourceLabStatusBadge("CONTROL LOCKED", SourceLabTone.ERROR)
                            Text("Owner control verification failed. Read-only state remains usable.", fontWeight = FontWeight.Bold)
                            Text(error, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
                        SourceLabCard(tone = SourceLabTone.ERROR) {
                            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                SourceLabStatusBadge("ADVANCED · RECOVERY", SourceLabTone.ERROR)
                                Text("Approval pipeline requires recovery", fontWeight = FontWeight.Bold)
                                Text(
                                    "Routine automation is paused. Only the exact fail-closed recovery action exposed by the backend is available.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                SourceLabSecondaryButton(
                                    text = "Open Recovery Dashboard",
                                    onClick = { context.startActivity(Intent(context, OwnerControlActivity::class.java)) },
                                    modifier = Modifier.fillMaxWidth(),
                                    icon = SourceLabIconKind.WARNING,
                                )
                            }
                        }
                    }
                }
            }

            item(key = "refresh") {
                SourceLabSecondaryButton(
                    text = if (state.refreshing) "Refreshing state…" else "Refresh state",
                    onClick = { scope.launch { refresh() } },
                    enabled = !state.initialLoading && !state.refreshing && !approving && !approvingReadySources,
                    modifier = Modifier.fillMaxWidth(),
                    icon = SourceLabIconKind.REFRESH,
                )
            }

            item(key = "boundary") {
                Text(
                    "Discovery, real-parser validation, pack sync, build, and release are automatic. Failed or HELD sources never advance. Human approval remains the routine mutation boundary.",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        SourceLabBottomBar(
            selected = SourceLabDestination.FARM,
            onSelect = { destination -> openSourceLabDestination(context, destination) },
            modifier = Modifier.align(Alignment.BottomCenter).padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }

}

@Composable
private fun PendingSourceApprovalCard(
    pending: LivePendingWorkerState,
    availability: SourceLabActionAvailability?,
    approving: Boolean,
    onApprove: () -> Unit,
) {
    val ready = pending.readyCount
    val available = ready > 0 && availability?.available == true
    SourceLabCard {
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Source Onboarding", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text(
                        if (ready > 0) {
                            "$ready real-parser validated source${if (ready == 1) "" else "s"} waiting for your approval."
                        } else {
                            "The bot is processing PENDING sources automatically."
                        },
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                SourceLabStatusBadge(
                    if (ready > 0) "$ready READY" else "AUTOMATIC",
                    if (ready > 0) SourceLabTone.WARNING else SourceLabTone.GOOD,
                )
            }

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SourceOnboardingMetric("Retry", pending.retryCount, Modifier.weight(1f))
                SourceOnboardingMetric("Held", pending.needsAttentionCount, Modifier.weight(1f))
                SourceOnboardingMetric("Approved", pending.approvedCount, Modifier.weight(1f))
            }

            if (ready > 0) {
                Button(
                    onClick = onApprove,
                    enabled = available && !approving,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (approving) {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.size(8.dp))
                        Text("Approving")
                    } else {
                        Text("Approve Ready Sources")
                    }
                }
                if (!available) {
                    Text(
                        "Approval is locked until the owner capability and live worker evidence are revalidated${availability?.reason?.let { " · $it" }.orEmpty()}.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun SourceOnboardingMetric(
    label: String,
    value: Int,
    modifier: Modifier = Modifier,
) {
    Surface(modifier = modifier, shape = androidx.compose.foundation.shape.RoundedCornerShape(10.dp), color = SourceLabSurface) {
        Column(Modifier.padding(9.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value.toString(), fontWeight = FontWeight.Bold)
            Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun RoutineStateCard(
    state: RoutineFarmState,
    snapshot: LiveFarmSnapshot,
    approvalAvailability: SourceLabActionAvailability?,
    publishRecoveryAvailability: SourceLabActionAvailability?,
    approving: Boolean,
    onReview: () -> Unit,
    onApprove: () -> Unit,
    onPublishRecovery: () -> Unit,
    onExceptions: () -> Unit,
    onDiagnostics: () -> Unit,
) {
    val candidate = snapshot.approvalCandidate
    val presentation = when (state) {
        RoutineFarmState.ALL_GOOD -> Triple("All good", "No action required. Upstream monitoring and Farm checks run automatically.", SourceLabTone.GOOD)
        RoutineFarmState.APPROVAL_REQUIRED -> Triple("1 update ready", "Candidate passed the safety gates and is waiting for your decision.", SourceLabTone.WARNING)
        RoutineFarmState.PUBLISHING -> {
            if (publishRecoveryAvailability?.available == true) {
                Triple(
                    "Publish needs recovery",
                    "The exact approved provider state is already signed, but publish has not completed. Resume the exact publish safely.",
                    SourceLabTone.WARNING,
                )
            } else {
                Triple(
                    "Publishing approved update",
                    "The approved pipeline is finishing automatically.",
                    SourceLabTone.ACCENT,
                )
            }
        }
        RoutineFarmState.HELD -> Triple("Held / safely blocked", "The bot could not safely advance this candidate. Last-known-good remains active.", SourceLabTone.WARNING)
        RoutineFarmState.INFRASTRUCTURE_FAILURE -> Triple("Infrastructure failure", "Automation needs attention. Last-known-good remains the safe active baseline.", SourceLabTone.ERROR)
    }

    SourceLabCard(tone = presentation.third) {
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
                RoutineFarmState.PUBLISHING -> {
                    if (publishRecoveryAvailability?.available == true) {
                        Button(onClick = onPublishRecovery, modifier = Modifier.fillMaxWidth()) {
                            Text("Resume Publish")
                        }
                    }
                }
                RoutineFarmState.HELD -> OutlinedButton(onClick = onExceptions, modifier = Modifier.fillMaxWidth()) { Text("Open Exceptions") }
                RoutineFarmState.INFRASTRUCTURE_FAILURE -> {
                    if (publishRecoveryAvailability?.available == true) {
                        Button(onClick = onPublishRecovery, modifier = Modifier.fillMaxWidth()) {
                            Text("Resume Publish")
                        }
                    } else {
                        OutlinedButton(onClick = onDiagnostics, modifier = Modifier.fillMaxWidth()) { Text("Open Diagnostics") }
                    }
                }
                RoutineFarmState.ALL_GOOD -> Unit
            }
        }
    }
}

private fun resolveRoutineFarmState(snapshot: LiveFarmSnapshot): RoutineFarmState {
    // Explicit backend failure/hold state must win over inferred lifecycle state.
    // Otherwise a failed publish with no lastPublish marker is misreported forever
    // as "PUBLISHING / no action required".
    when (snapshot.automation?.state) {
        "INFRASTRUCTURE_FAILURE" -> return RoutineFarmState.INFRASTRUCTURE_FAILURE
        "HELD" -> return RoutineFarmState.HELD
    }
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
        "ALL_GOOD", null -> RoutineFarmState.ALL_GOOD
        else -> RoutineFarmState.INFRASTRUCTURE_FAILURE
    }
}
