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
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class OwnerControlActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            OwnerControlTheme {
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

private sealed interface OwnerDashboardState {
    data object Loading : OwnerDashboardState
    data class Ready(
        val snapshot: LiveFarmSnapshot,
        val control: SourceLabResolvedControlState,
    ) : OwnerDashboardState
    data class Failed(val reason: String) : OwnerDashboardState
}

private sealed interface OwnerInventoryState {
    data object Loading : OwnerInventoryState
    data class Ready(val snapshot: SourceInventorySnapshot) : OwnerInventoryState
    data class Failed(val reason: String) : OwnerInventoryState
}

@Composable
private fun OwnerControlTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Color(0xFF8175FF),
            secondary = Color(0xFFA780FF),
            tertiary = Color(0xFF58D9C4),
            background = Color(0xFF0B0E14),
            surface = Color(0xFF111620),
            surfaceVariant = Color(0xFF19202C),
            onPrimary = Color.White,
            onBackground = Color(0xFFF4F6FA),
            onSurface = Color(0xFFF4F6FA),
            onSurfaceVariant = Color(0xFFB8C0CC),
            error = Color(0xFFFF6B74),
        ),
        content = content,
    )
}

@Composable
private fun OwnerControlScreen() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    var refreshKey by remember { mutableIntStateOf(0) }
    var inventoryRefreshKey by remember { mutableIntStateOf(0) }
    var state by remember { mutableStateOf<OwnerDashboardState>(OwnerDashboardState.Loading) }
    var inventoryState by remember { mutableStateOf<OwnerInventoryState>(OwnerInventoryState.Loading) }
    var runningAction by remember { mutableStateOf<SourceLabControlAction?>(null) }
    var confirmation by remember { mutableStateOf<SourceLabControlAction?>(null) }
    var operationMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(refreshKey) {
        state = OwnerDashboardState.Loading
        state = try {
            val snapshot = withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
            val control = SourceLabControlClient.resolveState(context, snapshot)
            OwnerDashboardState.Ready(snapshot, control)
        } catch (error: SourceLabControlException) {
            OwnerDashboardState.Failed(error.reason)
        } catch (error: Throwable) {
            OwnerDashboardState.Failed(error.message ?: error.javaClass.simpleName)
        }
    }

    LaunchedEffect(inventoryRefreshKey) {
        inventoryState = OwnerInventoryState.Loading
        inventoryState = try {
            OwnerInventoryState.Ready(
                SourceInventoryRepository.loadInventory(
                    context = context,
                    forceRefresh = inventoryRefreshKey > 0,
                ),
            )
        } catch (error: Throwable) {
            OwnerInventoryState.Failed(error.message ?: error.javaClass.simpleName)
        }
    }

    fun runAction(action: SourceLabControlAction, ready: OwnerDashboardState.Ready) {
        scope.launch {
            runningAction = action
            operationMessage = null
            try {
                if (action == SourceLabControlAction.APPROVE) {
                    val result = SourceLabControlClient.approveAndPublish(context, ready.snapshot)
                    operationMessage =
                        "APPROVE → PROMOTE → SIGN → PUBLISH · SUCCESS · " +
                            "runs ${result.approvalRunId}/${result.promotionRunId}/${result.signingRunId}/${result.publishRunId}"
                } else {
                    val result = SourceLabControlClient.execute(context, ready.snapshot, action)
                    operationMessage = "${action.name} · SUCCESS · run ${result.runId}"
                }
                refreshKey++
            } catch (error: SourceLabControlException) {
                operationMessage = "${action.name} · ${error.reason}"
                refreshKey++
            } catch (error: Throwable) {
                operationMessage = "${action.name} · ${error.message ?: error.javaClass.simpleName}"
                refreshKey++
            } finally {
                runningAction = null
            }
        }
    }

    val ready = state as? OwnerDashboardState.Ready
    if (confirmation != null && ready != null) {
        val action = confirmation!!
        AlertDialog(
            onDismissRequest = { if (runningAction == null) confirmation = null },
            title = {
                Text(
                    if (action == SourceLabControlAction.APPROVE) {
                        "Confirm APPROVE → PUBLISH"
                    } else if (action == SourceLabControlAction.PUBLISH) {
                        "Confirm OFFICIAL PUBLISH"
                    } else {
                        "Confirm ${action.name}"
                    },
                    fontWeight = FontWeight.Bold,
                )
            },
            text = {
                Text(
                    confirmationText(action, ready.snapshot, ready.control),
                    fontFamily = FontFamily.Monospace,
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        confirmation = null
                        runAction(action, ready)
                    },
                    enabled = runningAction == null,
                ) {
                    Text(
                        when (action) {
                            SourceLabControlAction.APPROVE -> "APPROVE & AUTO PUBLISH"
                            SourceLabControlAction.PUBLISH -> "PUBLISH OFFICIAL RELEASE"
                            else -> "CONFIRM ${action.name}"
                        },
                    )
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmation = null }) { Text("Cancel") }
            },
        )
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Text(
                "Miyorare Source Lab",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                "Compatibility Farm Owner control plane · v${BuildConfig.VERSION_NAME}",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        item {
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF123229))) {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("OWNER · AUTHORIZED", color = Color(0xFF75E8B0), fontWeight = FontWeight.Bold)
                    when (val current = state) {
                        OwnerDashboardState.Loading -> {
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                CircularProgressIndicator()
                                Text("Refreshing identity, backend proof, capabilities, and live Farm state…")
                            }
                        }
                        is OwnerDashboardState.Failed -> {
                            Text("CONTROL LOCKED · ${current.reason}", color = MaterialTheme.colorScheme.error)
                            OutlinedButton(onClick = { refreshKey++ }) { Text("Retry authorization") }
                        }
                        is OwnerDashboardState.Ready -> {
                            Text(
                                "Backend capability proof: ${current.control.session.backendCapabilities.size}/" +
                                    SourceLabControlAction.entries.size,
                            )
                            Text("Branch: ${current.snapshot.branch}")
                            OutlinedButton(
                                onClick = {
                                    refreshKey++
                                    inventoryRefreshKey++
                                },
                                enabled = runningAction == null,
                            ) {
                                Text("Refresh live state")
                            }
                        }
                    }
                }
            }
        }

        operationMessage?.let { message ->
            item {
                Card {
                    Text(message, Modifier.fillMaxWidth().padding(14.dp), fontWeight = FontWeight.SemiBold)
                }
            }
        }

        if (ready != null) {
            item { LiveCycleCard(ready.snapshot) }
            item {
                SourceInventorySummaryCard(
                    state = inventoryState,
                    farmSnapshot = ready.snapshot,
                    onOpen = {
                        context.startActivity(Intent(context, SourceInventoryActivity::class.java))
                    },
                    onRetry = { inventoryRefreshKey++ },
                )
            }
            item { ExactEvidenceCard(ready.snapshot) }
            item { Text("Owner actions", fontWeight = FontWeight.Bold) }

            items(
                listOf(SourceLabControlAction.RUN_FARM, SourceLabControlAction.APPROVE),
                key = { it.name },
            ) { action ->
                val availability = ready.control.actions.getValue(action)
                OwnerActionCard(
                    availability = availability,
                    running = runningAction == action,
                    label = if (action == SourceLabControlAction.APPROVE) "APPROVE & AUTO PUBLISH" else null,
                    onClick = {
                        if (action == SourceLabControlAction.RUN_FARM) runAction(action, ready)
                        else confirmation = action
                    },
                )
            }

            val recoveryActions = listOf(
                SourceLabControlAction.PROMOTE,
                SourceLabControlAction.SIGN,
                SourceLabControlAction.PUBLISH,
            ).filter { ready.control.actions.getValue(it).available }
            if (recoveryActions.isNotEmpty()) {
                item {
                    Text("Recovery actions", fontWeight = FontWeight.Bold)
                    Text(
                        "Shown only when an automatic approval pipeline needs manual recovery.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                items(recoveryActions, key = { "recovery-${it.name}" }) { action ->
                    OwnerActionCard(
                        availability = ready.control.actions.getValue(action),
                        running = runningAction == action,
                        onClick = { confirmation = action },
                    )
                }
            }

            item {
                Text(
                    "Normal lifecycle: RUN FARM → one Owner APPROVE → automatic PROMOTE → SIGN → PUBLISH. " +
                        "All writes, promotion, attestation, enrollment, and publishing happen in GitHub Actions. " +
                        "The APK stores no repository write token, signing key, keystore, or signing password.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun SourceInventorySummaryCard(
    state: OwnerInventoryState,
    farmSnapshot: LiveFarmSnapshot,
    onOpen: () -> Unit,
    onRetry: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Text("SOURCE INVENTORY", fontWeight = FontWeight.Bold)
            when (state) {
                OwnerInventoryState.Loading -> {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        CircularProgressIndicator(modifier = Modifier.height(20.dp))
                        Text("Loading automatic upstream inventory…")
                    }
                }
                is OwnerInventoryState.Failed -> {
                    Text("Inventory unavailable · Farm controls remain independent.", color = MaterialTheme.colorScheme.error)
                    Text(state.reason, style = MaterialTheme.typography.bodySmall)
                    OutlinedButton(onClick = onRetry) { Text("Retry inventory") }
                }
                is OwnerInventoryState.Ready -> {
                    val summary = state.snapshot.summary(farmSnapshot.sources.map { it.canonicalId }.toSet())
                    Text("All Sources       ${summary.allSources}")
                    Text("In Farm           ${summary.inFarm}")
                    Text("Not Enrolled      ${summary.notEnrolled}")
                    Text("Needs Attention   ${summary.needsAttention}")
                    val cacheNote = when {
                        state.snapshot.staleCacheFallback -> " · stale cache fallback"
                        state.snapshot.fromCache -> " · cached"
                        else -> ""
                    }
                    Text(
                        "${state.snapshot.branch} · ${state.snapshot.branchCommit.take(12)}$cacheNote",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Button(onClick = onOpen, modifier = Modifier.fillMaxWidth()) {
                        Text("OPEN ALL SOURCES")
                    }
                }
            }
        }
    }
}

@Composable
private fun LiveCycleCard(snapshot: LiveFarmSnapshot) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("LIVE · CONTROL ENABLED", color = Color(0xFF75E8B0), fontWeight = FontWeight.Bold)
            Text("Sources ${snapshot.sources.size}/${snapshot.targetSize} · ${snapshot.cohort}")
            when {
                snapshot.approvalCandidate != null -> {
                    Text("State · ${snapshot.approvalCandidate.state}", fontWeight = FontWeight.Bold)
                    Text("Candidate · ${snapshot.approvalCandidate.candidateSetId}", fontFamily = FontFamily.Monospace)
                }
                snapshot.lastPromotion != null && snapshot.lastPublish?.candidateSetId != snapshot.lastPromotion.candidateSetId -> {
                    Text("State · PROMOTED · automatic pipeline/recovery pending", fontWeight = FontWeight.Bold)
                    Text("Candidate · ${snapshot.lastPromotion.candidateSetId}", fontFamily = FontFamily.Monospace)
                }
                snapshot.lastPublish != null -> {
                    Text("State · PUBLISHED", fontWeight = FontWeight.Bold)
                    Text("${snapshot.lastPublish.tag} · release run ${snapshot.lastPublish.releaseRunId}")
                }
                else -> Text("State · READY FOR FARM", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun ExactEvidenceCard(snapshot: LiveFarmSnapshot) {
    val candidate = snapshot.approvalCandidate
    val promotion = snapshot.lastPromotion
    Card {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Exact live target", fontWeight = FontWeight.Bold)
            if (candidate != null) {
                Text("candidateSetId", style = MaterialTheme.typography.labelSmall)
                Mono(candidate.candidateSetId)
                candidate.providers.forEach { (provider, item) ->
                    Text(provider.uppercase(), fontWeight = FontWeight.SemiBold)
                    Mono("current   ${item.current}")
                    Mono("candidate ${item.candidate}")
                }
                Text("Evidence binding", fontWeight = FontWeight.SemiBold)
                Mono("farm   ${candidate.evidenceBinding.farmEvidenceSha256}")
                Mono("gate   ${candidate.evidenceBinding.gateSha256}")
                Mono("repair ${candidate.evidenceBinding.repairEvidenceSha256}")
                Mono("gateFingerprint ${candidate.gateFingerprint}")
                Text("publishEligible=${candidate.publishEligible}")
            } else if (promotion != null) {
                Text("candidateSetId", style = MaterialTheme.typography.labelSmall)
                Mono(promotion.candidateSetId)
                promotion.providers.forEach { (provider, commit) -> Mono("${provider.uppercase()} $commit") }
                Mono("promotionRunId ${promotion.promotionRunId}")
                snapshot.lastPublish?.takeIf { it.candidateSetId == promotion.candidateSetId }?.let { published ->
                    Mono("published ${published.tag}")
                    Mono("publishRunId ${published.publishRunId}")
                }
            } else {
                Text("No candidate is staged. Run Farm will evaluate live upstream state.")
            }
        }
    }
}

@Composable
private fun OwnerActionCard(
    availability: SourceLabActionAvailability,
    running: Boolean,
    label: String? = null,
    onClick: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(label ?: availability.action.name.replace('_', ' '), fontWeight = FontWeight.Bold)
                Surface(
                    shape = RoundedCornerShape(999.dp),
                    color = if (availability.available) Color(0xFF123229) else Color(0xFF2A2024),
                ) {
                    Text(
                        if (availability.available) "AVAILABLE" else "LOCKED",
                        Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        color = if (availability.available) Color(0xFF75E8B0) else MaterialTheme.colorScheme.error,
                    )
                }
            }
            Text(availability.reason, color = MaterialTheme.colorScheme.onSurfaceVariant)
            availability.prerequisiteRunId?.let { Mono("prerequisiteRunId $it") }
            Button(
                onClick = onClick,
                enabled = availability.available && !running,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (running) CircularProgressIndicator(modifier = Modifier.height(20.dp))
                else Text(label ?: availability.action.name.replace('_', ' '))
            }
        }
    }
}

@Composable
private fun Mono(text: String) {
    Text(text, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
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
            lines += "One confirmation starts APPROVE → PROMOTE → SIGN → PUBLISH automatically."
            lines += "Each stage reloads live state and revalidates its exact prerequisite."
        }
        SourceLabControlAction.PROMOTE -> lines += "approvalRunId=${control.approvalRunId ?: "MISSING"}"
        SourceLabControlAction.SIGN -> lines += "Signing: GitHub Artifact Attestation only"
        SourceLabControlAction.PUBLISH -> {
            lines += "signingRunId=${control.signingRunId ?: "MISSING"}"
            lines += "This creates an OFFICIAL immutable Source Pack GitHub release."
            lines += "Version is resolved server-side as the next Source Pack patch version."
        }
        else -> Unit
    }
    lines += "Server revalidates every SHA/evidence/run before mutation."
    return lines.joinToString("\n")
}
