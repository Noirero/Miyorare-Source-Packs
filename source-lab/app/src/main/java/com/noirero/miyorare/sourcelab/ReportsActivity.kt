package com.noirero.miyorare.sourcelab

import android.content.Intent
import android.net.Uri
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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class ReportsActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceLabPhase1Theme {
                SourceLabAppSurface {
                    ReportsScreen(onClose = { finish() })
                }
            }
        }
    }
}

private data class ReportsUiState(
    val snapshot: LiveFarmSnapshot? = null,
    val initialLoading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
)

@Composable
private fun ReportsScreen(onClose: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var ui by remember { mutableStateOf(ReportsUiState()) }

    suspend fun refresh() {
        val hasData = ui.snapshot != null
        ui = ui.copy(initialLoading = !hasData, refreshing = hasData, error = null)
        val result = runCatching {
            withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
        }
        ui = ui.copy(
            snapshot = result.getOrNull() ?: ui.snapshot,
            initialLoading = false,
            refreshing = false,
            error = result.exceptionOrNull()?.let { it.message ?: it.javaClass.simpleName },
        )
    }

    LaunchedEffect(Unit) { refresh() }

    val snapshot = ui.snapshot
    Box(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 16.dp, top = 16.dp, end = 16.dp, bottom = 96.dp),
            verticalArrangement = Arrangement.spacedBy(11.dp),
        ) {
            item(key = "header") {
                SourceLabTopBar(
                    title = "Reports",
                    subtitle = "Compatibility Farm history and release state.",
                    trailing = {
                        SourceLabIconButton(
                            icon = SourceLabIconKind.REFRESH,
                            contentDescription = "Refresh reports",
                            onClick = { scope.launch { refresh() } },
                            enabled = !ui.initialLoading && !ui.refreshing,
                        )
                    },
                )
            }

            if (ui.initialLoading && snapshot == null) {
                item(key = "loading") {
                    SourceLabCard(tone = SourceLabTone.ACCENT) {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp, color = SourceLabPrimary)
                            Column(Modifier.weight(1f)) {
                                Text("Loading Farm report", fontWeight = FontWeight.Bold)
                                Text(
                                    "Reading current Farm state and recent workflow runs.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }

            ui.error?.let { error ->
                item(key = "error") {
                    SourceLabCard(tone = SourceLabTone.WARNING) {
                        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            SourceLabStatusBadge("REFRESH FAILED", SourceLabTone.WARNING)
                            Text(error, style = MaterialTheme.typography.bodySmall)
                            if (snapshot != null) {
                                Text(
                                    "Previously loaded report data is retained.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }

            if (snapshot != null) {
                item(key = "summary") { FarmReportSummary(snapshot) }
                item(key = "providers") { ProviderHealthReport(snapshot.providers) }

                item(key = "runs-title") {
                    Text("Recent Farm Runs", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text(
                        "Logs stay load-on-demand; open a run only when you need the full GitHub Actions report.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }

                if (snapshot.recentRuns.isEmpty()) {
                    item(key = "runs-empty") {
                        SourceLabCard {
                            Text(
                                "No recent Compatibility Farm runs were returned by the backend.",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                } else {
                    items(snapshot.recentRuns, key = { it.id }, contentType = { "farm-run" }) { run ->
                        FarmRunReportRow(run) {
                            if (run.htmlUrl.isNotBlank()) {
                                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(run.htmlUrl)))
                            }
                        }
                    }
                }

                item(key = "release") { ReleaseStateReport(snapshot) }
            }
        }

        SourceLabBottomBar(
            selected = SourceLabDestination.REPORTS,
            onSelect = { destination -> openSourceLabDestination(context, destination) },
            modifier = Modifier.align(Alignment.BottomCenter).padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }


}

@Composable
private fun FarmReportSummary(snapshot: LiveFarmSnapshot) {
    val latest = snapshot.recentRuns.firstOrNull()
    val latestStatus = latest?.let { reportRunLabel(it) } ?: "No runs"
    val latestTone = latest?.let { reportRunTone(it) } ?: SourceLabTone.NEUTRAL
    SourceLabCard {
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(11.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Compatibility Farm", fontWeight = FontWeight.Bold)
                SourceLabStatusBadge(latestStatus, latestTone)
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                ReportMetric("In Farm", snapshot.sources.size.toString(), Modifier.weight(1f))
                ReportMetric("Providers", snapshot.providers.size.toString(), Modifier.weight(1f))
                ReportMetric("Candidate", if (snapshot.approvalCandidate != null) "1" else "0", Modifier.weight(1f))
            }
            latest?.let {
                Text(
                    "Latest run #${it.runNumber} · ${it.title}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun ReportMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(10.dp), color = SourceLabSurface) {
        Column(Modifier.padding(10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ProviderHealthReport(providers: List<LiveProviderState>) {
    SourceLabCard {
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Text("Provider Health", fontWeight = FontWeight.Bold)
            if (providers.isEmpty()) {
                Text("No provider state available.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                providers.forEach { provider ->
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(reportProviderName(provider.id), fontWeight = FontWeight.SemiBold)
                            Text(
                                provider.updateState.replace('_', ' '),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        val health = provider.runtimeHealth.uppercase()
                        SourceLabStatusBadge(
                            health.replace('_', ' '),
                            when (health) {
                                "HEALTHY", "PASS", "READY" -> SourceLabTone.GOOD
                                "BROKEN", "FAILED", "FAIL" -> SourceLabTone.ERROR
                                "DEGRADED", "HELD", "REVIEW" -> SourceLabTone.WARNING
                                else -> SourceLabTone.NEUTRAL
                            },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun FarmRunReportRow(run: LiveFarmRun, onOpen: () -> Unit) {
    SourceLabCard {
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(run.title, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(
                        "Run #${run.runNumber}${run.createdAt.takeIf { it.isNotBlank() }?.let { " · $it" }.orEmpty()}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                SourceLabStatusBadge(reportRunLabel(run), reportRunTone(run))
            }
            if (run.htmlUrl.isNotBlank()) {
                OutlinedButton(onClick = onOpen, modifier = Modifier.fillMaxWidth()) {
                    Text("View Full Report")
                }
            }
        }
    }
}

@Composable
private fun ReleaseStateReport(snapshot: LiveFarmSnapshot) {
    SourceLabCard {
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Text("Release State", fontWeight = FontWeight.Bold)
            snapshot.lastPromotion?.let { promotion ->
                Text("Last promotion", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall)
                Text(
                    "Candidate ${shortReportRef(promotion.candidateSetId)} · run ${promotion.promotionRunId}",
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                )
            } ?: Text("No promotion state available.", color = MaterialTheme.colorScheme.onSurfaceVariant)

            snapshot.lastPublish?.let { publish ->
                Text("Last published source pack", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall)
                Text("${publish.version} · ${publish.tag}", fontWeight = FontWeight.SemiBold)
                Text(
                    "Publish run ${publish.publishRunId} · release run ${publish.releaseRunId}",
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } ?: Text("No published Source Pack state available.", color = MaterialTheme.colorScheme.onSurfaceVariant)

            snapshot.approvalCandidate?.let { candidate ->
                Text("Live candidate", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall)
                Text(
                    "${shortReportRef(candidate.candidateSetId)} · ${candidate.state.replace('_', ' ')}",
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

private fun reportRunLabel(run: LiveFarmRun): String =
    (run.conclusion?.takeIf { it.isNotBlank() } ?: run.status).uppercase().replace('_', ' ')

private fun reportRunTone(run: LiveFarmRun): SourceLabTone = when (
    (run.conclusion?.takeIf { it.isNotBlank() } ?: run.status).lowercase()
) {
    "success" -> SourceLabTone.GOOD
    "failure", "cancelled", "timed_out", "action_required", "startup_failure" -> SourceLabTone.ERROR
    "in_progress", "queued", "requested", "waiting", "pending" -> SourceLabTone.ACCENT
    else -> SourceLabTone.NEUTRAL
}

private fun reportProviderName(value: String): String = when (value.lowercase()) {
    "keiyoushi" -> "Keiyoushi"
    "uma" -> "UMA"
    "gekkoushi" -> "Gekkoushi"
    else -> value.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
}

private fun shortReportRef(value: String): String = if (value.length > 14) value.take(14) else value
