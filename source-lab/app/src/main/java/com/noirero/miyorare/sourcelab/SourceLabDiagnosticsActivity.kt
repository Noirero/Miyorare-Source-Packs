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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
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
    val context = LocalContext.current
    var refreshKey by remember { mutableStateOf(0) }
    var state by remember { mutableStateOf(DiagnosticsState()) }

    LaunchedEffect(refreshKey) {
        val previous = state
        state = state.copy(loading = true, error = null, inventoryError = null)
        coroutineScope {
            val liveJob = async {
                runCatching {
                    val snapshot = withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
                    snapshot to SourceLabControlClient.resolveState(context, snapshot)
                }
            }
            val inventoryJob = async {
                runCatching { SourceInventoryRepository.loadInventory(context, forceRefresh = false) }
            }
            val live = liveJob.await()
            val inventory = inventoryJob.await()
            state = DiagnosticsState(
                loading = false,
                snapshot = live.getOrNull()?.first ?: previous.snapshot,
                control = live.getOrNull()?.second ?: previous.control,
                inventory = inventory.getOrNull() ?: previous.inventory,
                error = live.exceptionOrNull()?.let { it.message ?: it.javaClass.simpleName },
                inventoryError = inventory.exceptionOrNull()?.let { it.message ?: it.javaClass.simpleName },
            )
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "header") {
            SourceLabTopBar(
                title = "Diagnostics",
                subtitle = "Runtime, capability proof, Farm state, and inventory metadata.",
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
        if (snapshot != null && control != null) {
            item(key = "runtime") {
                DiagnosticCard("Runtime") {
                    DiagnosticLine("App version", BuildConfig.VERSION_NAME)
                    DiagnosticLine("Farm branch", snapshot.branch, true)
                    DiagnosticLine("Farm sources", "${snapshot.sources.size}/${snapshot.targetSize}")
                    DiagnosticLine("Cohort", snapshot.cohort)
                    DiagnosticLine("Retrieved at", snapshot.retrievedAtEpochMs.toString(), true)
                }
            }
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
            snapshot.approvalCandidate?.let { candidate ->
                item(key = "candidate") {
                    DiagnosticCard("Approval candidate") {
                        DiagnosticLine("candidateSetId", candidate.candidateSetId, true)
                        DiagnosticLine("state", candidate.state)
                        DiagnosticLine("publishEligible", candidate.publishEligible.toString())
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
        Text(
            value,
            fontFamily = if (monospace) FontFamily.Monospace else FontFamily.Default,
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
