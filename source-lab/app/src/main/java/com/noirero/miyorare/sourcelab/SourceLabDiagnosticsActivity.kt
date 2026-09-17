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
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    SourceLabDiagnosticsScreen(onClose = { finish() })
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
        state = state.copy(loading = true, error = null, inventoryError = null)
        coroutineScope {
            val liveDeferred = async {
                runCatching {
                    val snapshot = withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
                    snapshot to SourceLabControlClient.resolveState(context, snapshot)
                }
            }
            val inventoryDeferred = async {
                runCatching { SourceInventoryRepository.loadInventory(context, forceRefresh = false) }
            }
            val liveResult = liveDeferred.await()
            val inventoryResult = inventoryDeferred.await()
            state = DiagnosticsState(
                loading = false,
                snapshot = liveResult.getOrNull()?.first,
                control = liveResult.getOrNull()?.second,
                inventory = inventoryResult.getOrNull(),
                error = liveResult.exceptionOrNull()?.let { it.message ?: it.javaClass.simpleName },
                inventoryError = inventoryResult.exceptionOrNull()?.let { it.message ?: it.javaClass.simpleName },
            )
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "header") {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text("Diagnostics", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                    Text(
                        "Technical state and authorization proof",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                TextButton(onClick = onClose) { Text("Back") }
            }
        }

        if (state.loading) {
            item(key = "loading") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Row(
                        Modifier.fillMaxWidth().padding(16.dp),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        CircularProgressIndicator()
                        Text("Refreshing diagnostic state…")
                    }
                }
            }
        }

        state.error?.let { error ->
            item(key = "error") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
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
                    DiagnosticLine("Farm branch", snapshot.branch, monospace = true)
                    DiagnosticLine("Farm sources", "${snapshot.sources.size}/${snapshot.targetSize}")
                    DiagnosticLine("Cohort", snapshot.cohort)
                    DiagnosticLine("Retrieved at", snapshot.retrievedAtEpochMs.toString(), monospace = true)
                }
            }

            item(key = "capabilities") {
                DiagnosticCard("Backend capability proof") {
                    DiagnosticLine(
                        "Capabilities",
                        "${control.session.backendCapabilities.size}/${SourceLabControlAction.entries.size}",
                    )
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
                        DiagnosticLine("candidateSetId", candidate.candidateSetId, monospace = true)
                        DiagnosticLine("state", candidate.state)
                        DiagnosticLine("publishEligible", candidate.publishEligible.toString())
                        DiagnosticLine("farm evidence", candidate.evidenceBinding.farmEvidenceSha256, monospace = true)
                        DiagnosticLine("gate", candidate.evidenceBinding.gateSha256, monospace = true)
                        DiagnosticLine("repair", candidate.evidenceBinding.repairEvidenceSha256, monospace = true)
                        DiagnosticLine("gate fingerprint", candidate.gateFingerprint, monospace = true)
                    }
                }
            }

            snapshot.lastPromotion?.let { promotion ->
                item(key = "promotion") {
                    DiagnosticCard("Last promotion") {
                        DiagnosticLine("candidateSetId", promotion.candidateSetId, monospace = true)
                        DiagnosticLine("promotionRunId", promotion.promotionRunId.toString(), monospace = true)
                        DiagnosticLine("publishEligible", promotion.publishEligible.toString())
                    }
                }
            }

            snapshot.lastPublish?.let { published ->
                item(key = "publish") {
                    DiagnosticCard("Last publish") {
                        DiagnosticLine("candidateSetId", published.candidateSetId, monospace = true)
                        DiagnosticLine("version", published.version)
                        DiagnosticLine("tag", published.tag)
                        DiagnosticLine("signingRunId", published.signingRunId.toString(), monospace = true)
                        DiagnosticLine("publishRunId", published.publishRunId.toString(), monospace = true)
                        DiagnosticLine("releaseRunId", published.releaseRunId.toString(), monospace = true)
                    }
                }
            }
        }

        state.inventory?.let { inventory ->
            item(key = "inventory") {
                DiagnosticCard("Source inventory") {
                    DiagnosticLine("Branch", inventory.branch, monospace = true)
                    DiagnosticLine("Commit", inventory.branchCommit, monospace = true)
                    DiagnosticLine("Sources", inventory.sources.size.toString())
                    DiagnosticLine("Cached", inventory.fromCache.toString())
                    DiagnosticLine("Cache age ms", inventory.cacheAgeMillis.toString(), monospace = true)
                    DiagnosticLine("Stale fallback", inventory.staleCacheFallback.toString())
                    inventory.providerCommits.forEach { (provider, commit) ->
                        DiagnosticLine("${provider.prettyProviderName()} commit", commit, monospace = true)
                    }
                }
            }
        }

        state.inventoryError?.let { error ->
            item(key = "inventory-error") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
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
                "Diagnostics intentionally show runtime metadata and capability state only. Tokens, refresh tokens, signing keys, keystores, signing passwords, client secrets, and private keys are never displayed here.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun DiagnosticCard(title: String, content: @Composable () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
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
