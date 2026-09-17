package com.noirero.miyorare.sourcelab

import android.content.Intent
import android.net.Uri
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class ApprovalReviewActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceLabPhase1Theme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    ApprovalReviewScreen(onClose = { finish() })
                }
            }
        }
    }
}

private data class ApprovalReviewUiState(
    val snapshot: LiveFarmSnapshot? = null,
    val control: SourceLabResolvedControlState? = null,
    val comparisons: Map<String, ProviderComparisonSummary> = emptyMap(),
    val loading: Boolean = true,
    val comparing: Boolean = false,
    val actionRunning: Boolean = false,
    val error: String? = null,
    val comparisonError: String? = null,
    val operation: String? = null,
)

internal data class ProviderComparisonSummary(
    val provider: String,
    val repository: String,
    val current: String,
    val candidate: String,
    val status: String,
    val aheadBy: Int,
    val behindBy: Int,
    val totalCommits: Int,
    val changedFiles: Int,
    val additions: Int,
    val deletions: Int,
    val htmlUrl: String,
)

@Composable
private fun ApprovalReviewScreen(onClose: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var ui by remember { mutableStateOf(ApprovalReviewUiState()) }
    var confirmApprove by remember { mutableStateOf(false) }

    suspend fun loadReview(keepOperation: Boolean = true) {
        ui = ui.copy(loading = ui.snapshot == null, error = null)
        try {
            val snapshot = withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
            val control = SourceLabControlClient.resolveState(context, snapshot)
            ui = ui.copy(
                snapshot = snapshot,
                control = control,
                loading = false,
                error = null,
                operation = if (keepOperation) ui.operation else null,
            )

            val candidate = snapshot.approvalCandidate
            if (candidate != null) {
                ui = ui.copy(comparing = true, comparisonError = null)
                val comparisonResult = runCatching {
                    ProviderComparisonRepository.load(candidate)
                }
                ui = ui.copy(
                    comparisons = comparisonResult.getOrDefault(emptyMap()),
                    comparing = false,
                    comparisonError = comparisonResult.exceptionOrNull()?.let {
                        it.message ?: it.javaClass.simpleName
                    },
                )
            } else {
                ui = ui.copy(comparisons = emptyMap(), comparing = false, comparisonError = null)
            }
        } catch (error: SourceLabControlException) {
            ui = ui.copy(
                loading = false,
                error = error.reason,
                control = null,
            )
        } catch (error: Throwable) {
            ui = ui.copy(
                loading = false,
                error = error.message ?: error.javaClass.simpleName,
                control = null,
            )
        }
    }

    LaunchedEffect(Unit) { loadReview() }

    val snapshot = ui.snapshot
    val candidate = snapshot?.approvalCandidate
    val approval = ui.control?.actions?.get(SourceLabControlAction.APPROVE)

    if (confirmApprove && snapshot != null && candidate != null && approval?.available == true) {
        AlertDialog(
            onDismissRequest = { if (!ui.actionRunning) confirmApprove = false },
            title = { Text("Approve candidate & continue publish", fontWeight = FontWeight.Bold) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        "This starts the real APPROVE → PROMOTE → SIGN → PUBLISH pipeline for the live candidate.",
                    )
                    Text(
                        "Each stage reloads live state and the backend revalidates exact evidence and prerequisite runs. Source Lab signing material is not stored in the APK.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Text(
                        "Candidate ${shortCandidateId(candidate.candidateSetId)}",
                        fontFamily = FontFamily.Monospace,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            },
            confirmButton = {
                Button(
                    enabled = !ui.actionRunning,
                    onClick = {
                        confirmApprove = false
                        scope.launch {
                            ui = ui.copy(actionRunning = true, operation = null)
                            try {
                                val result = SourceLabControlClient.approveAndPublish(context, snapshot)
                                ui = ui.copy(
                                    actionRunning = false,
                                    operation = "Approve → Promote → Sign → Publish succeeded · runs ${result.approvalRunId}/${result.promotionRunId}/${result.signingRunId}/${result.publishRunId}",
                                )
                                loadReview(keepOperation = true)
                            } catch (error: SourceLabControlException) {
                                ui = ui.copy(actionRunning = false, operation = "Approval pipeline · ${error.reason}")
                                loadReview(keepOperation = true)
                            } catch (error: Throwable) {
                                ui = ui.copy(
                                    actionRunning = false,
                                    operation = "Approval pipeline · ${error.message ?: error.javaClass.simpleName}",
                                )
                                loadReview(keepOperation = true)
                            }
                        }
                    },
                ) { Text("Approve & Auto Publish") }
            },
            dismissButton = { TextButton(onClick = { confirmApprove = false }) { Text("Cancel") } },
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
                TextButton(onClick = onClose) { Text("← Dashboard") }
                OutlinedButton(
                    enabled = !ui.loading && !ui.actionRunning,
                    onClick = { scope.launch { loadReview() } },
                ) {
                    if (ui.loading) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                    else Text("Refresh")
                }
            }
            Text("Candidate Review", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(
                "Review real provider refs, compatibility state and diff summary before Owner approval.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        if (ui.loading && snapshot == null) {
            item(key = "loading") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Row(
                        Modifier.fillMaxWidth().padding(18.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                        Column {
                            Text("Loading live approval state", fontWeight = FontWeight.Bold)
                            Text(
                                "No approval action is enabled until Owner authorization and backend capability are resolved.",
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
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        SourceLabStatusBadge("CONTROL LOCKED", SourceLabTone.ERROR)
                        Text(error, color = MaterialTheme.colorScheme.error)
                        Text(
                            "The candidate may still be visible from the last successful read, but Owner mutation remains disabled.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        ui.operation?.let { message ->
            item(key = "operation") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Text(message, Modifier.fillMaxWidth().padding(14.dp), fontWeight = FontWeight.SemiBold)
                }
            }
        }

        if (!ui.loading && candidate == null && ui.error == null) {
            item(key = "empty") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        SourceLabStatusBadge("NO CANDIDATE", SourceLabTone.NEUTRAL)
                        Text("No candidate is waiting for approval.", fontWeight = FontWeight.Bold)
                        Text(
                            "Run Compatibility Farm from the dashboard to evaluate current upstream state. A review screen appears only when the backend stages a real candidate.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        if (candidate != null) {
            item(key = "summary") {
                CandidateSummaryCard(candidate, approval)
            }

            item(key = "versions-title") {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("Version Comparison", fontWeight = FontWeight.Bold)
                    if (ui.comparing) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                            Spacer(Modifier.size(6.dp))
                            Text("Comparing", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                Text(
                    "Diff metadata is loaded on demand. Large patch content is opened in GitHub instead of being preloaded into the dashboard.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            items(candidate.providers.entries.toList(), key = { it.key }) { entry ->
                ProviderComparisonCard(
                    provider = entry.key,
                    refs = entry.value,
                    comparison = ui.comparisons[entry.key],
                    comparing = ui.comparing,
                    onOpenDiff = { url ->
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                    },
                )
            }

            ui.comparisonError?.let { error ->
                item(key = "compare-warning") {
                    Card(colors = CardDefaults.cardColors(containerColor = SourceLabSurface)) {
                        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            SourceLabStatusBadge("DIFF METADATA UNAVAILABLE", SourceLabTone.WARNING)
                            Text(
                                "Provider refs remain authoritative and visible. Comparison summary could not be loaded: $error",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }

            item(key = "evidence") {
                CandidateEvidenceCard(candidate)
            }

            item(key = "approval-action") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Owner Approval", fontWeight = FontWeight.Bold)
                        val available = approval?.available == true && ui.error == null
                        SourceLabStatusBadge(
                            if (available) "READY FOR APPROVAL" else "LOCKED",
                            if (available) SourceLabTone.GOOD else SourceLabTone.NEUTRAL,
                        )
                        Text(
                            if (available) {
                                "The live candidate and Owner capability satisfy the client-side prerequisites. The backend will revalidate everything before mutation."
                            } else {
                                "Approval is unavailable: ${approval?.reason ?: ui.error ?: "OWNER_CONTROL_UNRESOLVED"}"
                            },
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Button(
                            enabled = available && !ui.actionRunning,
                            onClick = { confirmApprove = true },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            if (ui.actionRunning) {
                                CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                                Spacer(Modifier.size(8.dp))
                                Text("Publishing pipeline")
                            } else {
                                Text("Approve & Auto Publish")
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CandidateSummaryCard(
    candidate: LiveApprovalCandidate,
    approval: SourceLabActionAvailability?,
) {
    val waiting = candidate.state == "WAITING_FOR_APPROVAL"
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Compatibility Gate", fontWeight = FontWeight.Bold)
                    Text(
                        if (waiting) "Candidate passed the Farm gate and is waiting for Owner review." else candidate.state.replace('_', ' '),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                SourceLabStatusBadge(
                    if (waiting) "READY FOR REVIEW" else candidate.state.replace('_', ' '),
                    if (waiting) SourceLabTone.GOOD else SourceLabTone.WARNING,
                )
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                CandidateMetric("Providers", candidate.providers.size.toString(), Modifier.weight(1f))
                CandidateMetric("Repair evidence", candidate.evidenceBinding.repairEvidenceCount.toString(), Modifier.weight(1f))
            }
            Text(
                "Candidate · ${shortCandidateId(candidate.candidateSetId)}",
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (approval != null && !approval.available) {
                Text(
                    "Approval action locked · ${approval.reason}",
                    color = SourceLabWarning,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun CandidateMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(12.dp), color = SourceLabSurface) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ProviderComparisonCard(
    provider: String,
    refs: LiveCandidateProvider,
    comparison: ProviderComparisonSummary?,
    comparing: Boolean,
    onOpenDiff: (String) -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(providerReviewName(provider), fontWeight = FontWeight.Bold)
                when {
                    comparison != null -> SourceLabStatusBadge(
                        comparison.status.replace('_', ' ').uppercase(),
                        if (comparison.behindBy == 0) SourceLabTone.ACCENT else SourceLabTone.WARNING,
                    )
                    comparing -> CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    else -> SourceLabStatusBadge("REFS ONLY", SourceLabTone.NEUTRAL)
                }
            }

            VersionRef("Current", refs.current)
            VersionRef("Candidate", refs.candidate)

            if (comparison != null) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CompactMetric("Commits", comparison.totalCommits.toString(), Modifier.weight(1f))
                    CompactMetric("Files", comparison.changedFiles.toString(), Modifier.weight(1f))
                    CompactMetric("+ / -", "+${comparison.additions} / -${comparison.deletions}", Modifier.weight(1f))
                }
                Text(
                    "Ahead ${comparison.aheadBy} · Behind ${comparison.behindBy}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedButton(
                    onClick = { onOpenDiff(comparison.htmlUrl) },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("View Diff on GitHub") }
            }
        }
    }
}

@Composable
private fun VersionRef(label: String, value: String) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            shortRefForReview(value),
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun CompactMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(10.dp), color = SourceLabSurface) {
        Column(Modifier.padding(9.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
            Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun CandidateEvidenceCard(candidate: LiveApprovalCandidate) {
    Card(colors = CardDefaults.cardColors(containerColor = SourceLabSurface)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Evidence & Regression", fontWeight = FontWeight.Bold)
                SourceLabStatusBadge("BOUND", SourceLabTone.ACCENT)
            }
            Text(
                "The live candidate carries Farm, gate and repair evidence bindings. Full hashes remain available in Diagnostics instead of crowding this review screen.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                "Repair evidence records · ${candidate.evidenceBinding.repairEvidenceCount}",
                style = MaterialTheme.typography.bodySmall,
            )
            if (candidate.gateFingerprint.isNotBlank()) {
                Text(
                    "Gate fingerprint · ${shortRefForReview(candidate.gateFingerprint)}",
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                "Screenshot comparison is not shown because the current live candidate state does not expose screenshot artifacts to the APK. No placeholder result is fabricated.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

internal object ProviderComparisonRepository {
    private const val sourceRepo = "Noirero/Miyorare-Source-Packs"
    private const val apiAccept = "application/vnd.github+json"

    suspend fun load(candidate: LiveApprovalCandidate): Map<String, ProviderComparisonSummary> =
        withContext(Dispatchers.IO) {
            val repositories = loadProviderRepositories()
            coroutineScope {
                candidate.providers.map { (provider, refs) ->
                    async {
                        val repository = repositories[provider]
                            ?: error("Provider repository is not declared for $provider")
                        provider to loadProviderComparison(provider, repository, refs)
                    }
                }.awaitAll().toMap()
            }
        }

    internal fun parseComparison(
        provider: String,
        repository: String,
        current: String,
        candidate: String,
        payload: String,
    ): ProviderComparisonSummary {
        val root = JSONObject(payload)
        val files = root.optJSONArray("files")
        var additions = 0
        var deletions = 0
        if (files != null) {
            for (index in 0 until files.length()) {
                val file = files.getJSONObject(index)
                additions += file.optInt("additions", 0)
                deletions += file.optInt("deletions", 0)
            }
        }
        return ProviderComparisonSummary(
            provider = provider,
            repository = repository,
            current = current,
            candidate = candidate,
            status = root.optString("status", "unknown"),
            aheadBy = root.optInt("ahead_by", 0),
            behindBy = root.optInt("behind_by", 0),
            totalCommits = root.optInt("total_commits", 0),
            changedFiles = files?.length() ?: 0,
            additions = additions,
            deletions = deletions,
            htmlUrl = root.optString("html_url").ifBlank {
                "https://github.com/$repository/compare/$current...$candidate"
            },
        )
    }

    private fun loadProviderRepositories(): Map<String, String> {
        val url = "https://raw.githubusercontent.com/$sourceRepo/${SourceLabRepository.farmBranch}/upstream/registry.json"
        val root = JSONObject(fetchText(url))
        val providers = root.getJSONObject("providers")
        return providers.keys().asSequence().associateWith { provider ->
            providers.getJSONObject(provider).getString("repository")
        }
    }

    private fun loadProviderComparison(
        provider: String,
        repository: String,
        refs: LiveCandidateProvider,
    ): ProviderComparisonSummary {
        require(refs.current.matches(Regex("^[0-9a-f]{40}$"))) { "Invalid current ref for $provider" }
        require(refs.candidate.matches(Regex("^[0-9a-f]{40}$"))) { "Invalid candidate ref for $provider" }
        val payload = fetchText(
            "https://api.github.com/repos/$repository/compare/${refs.current}...${refs.candidate}",
        )
        return parseComparison(provider, repository, refs.current, refs.candidate, payload)
    }

    private fun fetchText(url: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10_000
            readTimeout = 20_000
            setRequestProperty("Accept", apiAccept)
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/${BuildConfig.VERSION_NAME}")
            useCaches = false
        }
        return try {
            val statusCode = connection.responseCode
            if (statusCode !in 200..299) {
                error("HTTP $statusCode while reading provider comparison")
            }
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }
}

private fun providerReviewName(value: String): String = when (value.lowercase()) {
    "keiyoushi" -> "Keiyoushi"
    "uma" -> "UMA"
    "gekkoushi" -> "Gekkoushi"
    else -> value.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
}

private fun shortCandidateId(value: String): String = if (value.length > 16) value.take(16) else value
private fun shortRefForReview(value: String): String = if (value.length > 12) value.take(12) else value
