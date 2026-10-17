package com.noirero.miyorare.sourcelab

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SourceLabDiagnosticsActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceLabPhase1Theme {
                SourceLabAppSurface {
                    SourceLabDiagnosticsScreen { finish() }
                }
            }
        }
    }
}

private data class DiagnosticsState(
    val loading: Boolean = true,
    val snapshot: LiveFarmSnapshot? = null,
    val control: SourceLabResolvedControlState? = null,
    val inventory: SourceInventorySnapshot? = null,
    val error: String? = null,
    val inventoryError: String? = null,
)

@Composable
private fun SourceLabDiagnosticsScreen(onClose: () -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    var refreshKey by remember { mutableStateOf(0) }
    var state by remember { mutableStateOf(DiagnosticsState()) }

    LaunchedEffect(refreshKey) {
        val previous = state
        state = state.copy(loading = true, error = null, inventoryError = null)
        coroutineScope {
            launch {
                val snapshotResult = runCatching {
                    withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
                }
                val snapshot = snapshotResult.getOrNull()
                if (snapshot == null) {
                    state = state.copy(
                        snapshot = previous.snapshot,
                        control = previous.control,
                        error = snapshotResult.exceptionOrNull()?.let {
                            it.message ?: it.javaClass.simpleName
                        },
                    )
                } else {
                    state = state.copy(snapshot = snapshot, error = null)
                    if (SourceLabOwnerSessionStore.isViewerModeRequested()) {
                        state = state.copy(control = null, error = null)
                    } else {
                        val controlResult = runCatching {
                            SourceLabControlClient.resolveState(context, snapshot)
                        }
                        state = state.copy(
                            control = controlResult.getOrNull(),
                            error = controlResult.exceptionOrNull()?.let {
                                if (it is SourceLabControlException) it.reason
                                else it.message ?: it.javaClass.simpleName
                            },
                        )
                    }
                }
            }

            launch {
                val inventoryResult = runCatching {
                    SourceInventoryRepository.loadInventory(context, forceRefresh = false)
                }
                state = state.copy(
                    inventory = inventoryResult.getOrNull() ?: previous.inventory,
                    inventoryError = inventoryResult.exceptionOrNull()?.let {
                        it.message ?: it.javaClass.simpleName
                    },
                )
            }
        }
        state = state.copy(loading = false)
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "header") {
            SourceLabTopBar(
                title = "Diagnostics",
                subtitle = "Runtime, capability proof, Farm authority, and inventory metadata.",
                onBack = onClose,
                trailing = {
                    SourceLabIconButton(
                        icon = SourceLabIconKind.REFRESH,
                        contentDescription = "Refresh diagnostics",
                        onClick = { refreshKey++ },
                        enabled = !state.loading,
                    )
                },
            )
        }

        if (state.loading) {
            item(key = "loading") {
                SourceLabCard(tone = SourceLabTone.ACCENT, contentPadding = PaddingValues(12.dp)) {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        CircularProgressIndicator(Modifier.padding(2.dp), strokeWidth = 2.dp, color = SourceLabPrimary)
                        Column(Modifier.weight(1f)) {
                            Text("Refreshing diagnostic state…", fontWeight = FontWeight.SemiBold)
                            if (state.snapshot != null || state.inventory != null) {
                                Text(
                                    "Previously loaded values remain visible while refreshing.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
        }

        state.error?.let { error ->
            item(key = "error") {
                SourceLabCard {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Live control diagnostics unavailable", color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.Bold)
                        Text(error)
                        Button(onClick = { refreshKey++ }) { Text("Retry") }
                    }
                }
            }
        }

        val snapshot = state.snapshot
        val control = state.control
        if (snapshot != null) {
            item(key = "runtime") {
                DiagnosticCard("Runtime") {
                    DiagnosticLine("App version", BuildConfig.VERSION_NAME)
                    DiagnosticLine("Farm branch", snapshot.branch, true)
                    DiagnosticLine("Farm commit", snapshot.farmCommit, true)
                    DiagnosticLine("Farm sources", "${snapshot.sources.size}/${snapshot.targetSize}")
                    DiagnosticLine("Cohort", snapshot.cohort)
                    DiagnosticLine("Retrieved at", snapshot.retrievedAtEpochMs.toString(), true)
                }
            }
            item(key = "provider-authority") {
                DiagnosticCard("Provider authority") {
                    snapshot.providers.forEach { provider ->
                        DiagnosticLine("${provider.id} updateState", provider.updateState)
                        DiagnosticLine("${provider.id} operational health", provider.runtimeHealth)
                        DiagnosticLine("${provider.id} active commit", provider.activeCommit, true)
                        DiagnosticLine("${provider.id} last-known-good", provider.lastKnownGood, true)
                        DiagnosticLine("${provider.id} release eligibility", provider.releaseEligibility)
                        provider.reason?.let {
                            DiagnosticLine("${provider.id} operational reason", it)
                        }
                        provider.releaseEligibilityReason?.let {
                            DiagnosticLine("${provider.id} eligibility reason", it)
                        }
                    }
                }
            }
            if (control != null) {
                item(key = "capabilities") {
                    DiagnosticCard("Backend capability proof") {
                        DiagnosticLine("Capabilities", "${control.session.backendCapabilities.size}/${SourceLabControlAction.entries.size}")
                        SourceLabControlAction.entries.forEach { action ->
                            val availability = control.actions[action]
                            DiagnosticLine(
                                action.name,
                                if (availability?.available == true) "AVAILABLE" else "LOCKED · ${availability?.reason ?: "unresolved"}",
                            )
                        }
                    }
                }
            }
            snapshot.approvalCandidate?.let { candidate ->
                item(key = "candidate") {
                    DiagnosticCard("Approval candidate") {
                        DiagnosticLine("candidateSetId", candidate.candidateSetId, true)
                        DiagnosticLine("state", candidate.state)
                        DiagnosticLine("publishEligible", candidate.publishEligible.toString())
                        candidate.providers.forEach { (provider, refs) ->
                            DiagnosticLine("$provider expected LKG", refs.current, true)
                            DiagnosticLine("$provider locked candidate", refs.candidate, true)
                            snapshot.providers.firstOrNull { it.id == provider }?.let { state ->
                                DiagnosticLine("$provider active commit", state.activeCommit, true)
                                DiagnosticLine("$provider current LKG", state.lastKnownGood, true)
                            }
                            snapshot.automation?.candidates?.get(provider)?.let { live ->
                                DiagnosticLine("$provider live upstream", live.candidate, true)
                            }
                            candidate.sourceScope[provider]?.let { scope ->
                                DiagnosticLine("$provider source scope", scope.joinToString("\n"), true)
                            }
                        }
                        DiagnosticLine("farm evidence", candidate.evidenceBinding.farmEvidenceSha256, true)
                        DiagnosticLine("gate", candidate.evidenceBinding.gateSha256, true)
                        DiagnosticLine("repair", candidate.evidenceBinding.repairEvidenceSha256, true)
                        DiagnosticLine("gate fingerprint", candidate.gateFingerprint, true)
                    }
                }
            }
            snapshot.lastPromotion?.let { promotion ->
                item(key = "promotion") {
                    DiagnosticCard("Last promotion") {
                        DiagnosticLine("candidateSetId", promotion.candidateSetId, true)
                        DiagnosticLine("promotionRunId", promotion.promotionRunId.toString(), true)
                        DiagnosticLine("publishEligible", promotion.publishEligible.toString())
                        promotion.providers.forEach { (provider, commit) ->
                            DiagnosticLine("$provider promoted commit", commit, true)
                        }
                        promotion.sourceScope.forEach { (provider, scope) ->
                            DiagnosticLine("$provider source scope", scope.joinToString("\n"), true)
                        }
                    }
                }
            }
            snapshot.lastPublish?.let { published ->
                item(key = "publish") {
                    DiagnosticCard("Last publish") {
                        DiagnosticLine("candidateSetId", published.candidateSetId, true)
                        DiagnosticLine("version", published.version)
                        DiagnosticLine("tag", published.tag)
                        DiagnosticLine("signingRunId", published.signingRunId.toString(), true)
                        DiagnosticLine("publishRunId", published.publishRunId.toString(), true)
                        DiagnosticLine("releaseRunId", published.releaseRunId.toString(), true)
                    }
                }
            }
        }

        state.inventory?.let { inventory ->
            item(key = "inventory") {
                DiagnosticCard("Source inventory") {
                    DiagnosticLine("Branch", inventory.branch, true)
                    DiagnosticLine("Commit", inventory.branchCommit, true)
                    DiagnosticLine("Sources", inventory.sources.size.toString())
                    DiagnosticLine("Cached", inventory.fromCache.toString())
                    DiagnosticLine("Cache age ms", inventory.cacheAgeMillis.toString(), true)
                    DiagnosticLine("Stale fallback", inventory.staleCacheFallback.toString())
                    inventory.providerCommits.forEach { (provider, commit) ->
                        DiagnosticLine("${provider.uppercase()} commit", commit, true)
                    }
                }
            }
        }

        state.inventoryError?.let { error ->
            item(key = "inventory-error") {
                SourceLabCard {
                    Text(
                        "Inventory diagnostics unavailable · $error",
                        Modifier.fillMaxWidth().padding(16.dp),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        }

        item(key = "privacy") {
            Text(
                "Diagnostics show runtime metadata and capability state only. Tokens, refresh tokens, signing keys, keystores, signing passwords, client secrets and private keys are never displayed here.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun DiagnosticCard(title: String, content: @Composable () -> Unit) {
    SourceLabCard {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

@Composable
private fun DiagnosticLine(label: String, value: String, monospace: Boolean = false) {
    Column {
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        SelectionContainer {
            Text(
                value,
                fontFamily = if (monospace) FontFamily.Monospace else FontFamily.Default,
                style = MaterialTheme.typography.bodySmall,
                maxLines = if (monospace) 8 else 4,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}
