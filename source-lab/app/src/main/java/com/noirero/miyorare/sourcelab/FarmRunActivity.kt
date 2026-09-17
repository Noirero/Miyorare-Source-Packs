package com.noirero.miyorare.sourcelab

import android.content.Context
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
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class FarmRunActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceLabPhase1Theme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    FarmRunScreen(onClose = { finish() })
                }
            }
        }
    }
}

private enum class FarmRunPhase {
    PREPARING,
    RUNNING,
    SUCCESS,
    FAILED,
}

private data class FarmRunUiState(
    val phase: FarmRunPhase = FarmRunPhase.PREPARING,
    val progress: MonitoredFarmRun? = null,
    val snapshot: LiveFarmSnapshot? = null,
    val result: SourceLabActionResult? = null,
    val error: String? = null,
    val startedAtEpochMs: Long = System.currentTimeMillis(),
)

internal data class MonitoredFarmStep(
    val name: String,
    val status: String,
    val conclusion: String?,
)

internal data class MonitoredFarmJob(
    val id: Long,
    val name: String,
    val status: String,
    val conclusion: String?,
    val steps: List<MonitoredFarmStep>,
)

internal data class MonitoredFarmRun(
    val id: Long,
    val runNumber: Int,
    val status: String,
    val conclusion: String?,
    val title: String,
    val htmlUrl: String,
    val jobs: List<MonitoredFarmJob>,
)

@Composable
private fun FarmRunScreen(onClose: () -> Unit) {
    val context = LocalContext.current
    var ui by remember { mutableStateOf(FarmRunUiState()) }
    var clockEpochMs by remember { mutableStateOf(System.currentTimeMillis()) }

    LaunchedEffect(ui.phase) {
        while (ui.phase == FarmRunPhase.PREPARING || ui.phase == FarmRunPhase.RUNNING) {
            clockEpochMs = System.currentTimeMillis()
            delay(1_000L)
        }
    }

    LaunchedEffect(Unit) {
        val baselineRunId: Long?
        val monitorToken: String?
        try {
            val stored = GitHubOwnerCredentialVault.load(context)
                ?: throw SourceLabControlException("OWNER_CREDENTIAL_REQUIRED")
            val identity = GitHubOwnerAuthentication.restoreOwnerLogin(
                GitHubOwnerAuthentication.resolveClientId(),
                stored,
            )
            GitHubOwnerCredentialVault.save(context, identity.credential)
            monitorToken = identity.accessToken
            baselineRunId = withContext(Dispatchers.IO) {
                FarmRunMonitor.latestOwnerRunId(monitorToken)
            }
        } catch (_: Throwable) {
            monitorToken = null
            baselineRunId = null
        }

        var monitorJob: Job? = null
        try {
            val snapshot = withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
            val control = SourceLabControlClient.resolveState(context, snapshot)
            val availability = control.actions.getValue(SourceLabControlAction.RUN_FARM)
            if (!availability.available) throw SourceLabControlException(availability.reason)

            ui = ui.copy(phase = FarmRunPhase.PREPARING, snapshot = snapshot, error = null)

            if (monitorToken != null && baselineRunId != null) {
                monitorJob = launch {
                    var discoveredRunId: Long? = null
                    var discoveryPolls = 0
                    while (isActive && ui.phase != FarmRunPhase.SUCCESS && ui.phase != FarmRunPhase.FAILED) {
                        val progress = runCatching {
                            withContext(Dispatchers.IO) {
                                if (discoveredRunId == null) {
                                    FarmRunMonitor.findOwnerRunAfter(monitorToken, baselineRunId)?.also {
                                        discoveredRunId = it.id
                                    }
                                } else {
                                    FarmRunMonitor.loadRun(monitorToken, discoveredRunId!!)
                                }
                            }
                        }.getOrNull()
                        if (progress != null) {
                            ui = ui.copy(
                                phase = if (progress.status == "completed") ui.phase else FarmRunPhase.RUNNING,
                                progress = progress,
                            )
                        }
                        discoveryPolls += 1
                        delay(if (discoveredRunId == null && discoveryPolls < 30) 2_500L else 8_000L)
                    }
                }
            }

            val result = SourceLabControlClient.execute(context, snapshot, SourceLabControlAction.RUN_FARM)
            monitorJob?.cancel()
            val finalProgress = monitorToken?.let { token ->
                runCatching { withContext(Dispatchers.IO) { FarmRunMonitor.loadRun(token, result.runId) } }.getOrNull()
            } ?: ui.progress
            val freshSnapshot = runCatching {
                withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
            }.getOrNull()
            ui = ui.copy(
                phase = FarmRunPhase.SUCCESS,
                progress = finalProgress ?: ui.progress,
                snapshot = freshSnapshot ?: ui.snapshot,
                result = result,
                error = null,
            )
        } catch (error: SourceLabControlException) {
            monitorJob?.cancel()
            val finalProgress = if (monitorToken != null && baselineRunId != null) {
                runCatching {
                    withContext(Dispatchers.IO) {
                        val known = ui.progress
                        if (known != null) FarmRunMonitor.loadRun(monitorToken, known.id)
                        else FarmRunMonitor.findOwnerRunAfter(monitorToken, baselineRunId)
                    }
                }.getOrNull()
            } else {
                ui.progress
            }
            val freshSnapshot = runCatching {
                withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() }
            }.getOrNull()
            ui = ui.copy(
                phase = FarmRunPhase.FAILED,
                progress = finalProgress ?: ui.progress,
                snapshot = freshSnapshot ?: ui.snapshot,
                error = error.reason,
            )
        } catch (error: Throwable) {
            monitorJob?.cancel()
            ui = ui.copy(
                phase = FarmRunPhase.FAILED,
                error = error.message ?: error.javaClass.simpleName,
            )
        }
    }

    val elapsedSeconds = ((clockEpochMs - ui.startedAtEpochMs).coerceAtLeast(0L)) / 1_000L
    val jobs = ui.progress?.jobs.orEmpty()
    val completedJobs = jobs.count { it.status == "completed" }
    val progressFraction = if (jobs.isNotEmpty()) completedJobs.toFloat() / jobs.size.toFloat() else 0f
    val currentJob = jobs.firstOrNull { it.status == "in_progress" }
        ?: jobs.firstOrNull { it.status in setOf("queued", "waiting", "pending") }
    val repairSteps = jobs.flatMap { job ->
        job.steps.filter { step -> step.name.contains("repair", ignoreCase = true) }
            .map { job.name to it }
    }
    val failedJobs = jobs.filter { jobStatus(it).first == "FAIL" }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "header") {
            TextButton(onClick = onClose) { Text("← Dashboard") }
            Text("Compatibility Farm Test", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(
                "Live status is read from the real Source Lab workflow. No test state is simulated in the APK.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
            )
        }

        item(key = "status") {
            FarmRunStatusCard(
                ui = ui,
                elapsedSeconds = elapsedSeconds,
                completedJobs = completedJobs,
                totalJobs = jobs.size,
                progressFraction = progressFraction,
                currentJob = currentJob,
            )
        }

        if (jobs.isNotEmpty()) {
            item(key = "jobs-title") {
                Text("Test progress", fontWeight = FontWeight.Bold)
            }
            items(jobs, key = { it.id }) { job ->
                FarmJobRow(job)
            }
        }

        if (repairSteps.isNotEmpty()) {
            item(key = "repair") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Repair / retest evidence", fontWeight = FontWeight.Bold)
                        repairSteps.forEach { (jobName, step) ->
                            val status = stepStatus(step)
                            Row(
                                Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Column(Modifier.weight(1f)) {
                                    Text(step.name, fontWeight = FontWeight.SemiBold)
                                    Text(jobName, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                                SourceLabStatusBadge(status.first, status.second)
                            }
                        }
                    }
                }
            }
        }

        if (ui.phase == FarmRunPhase.SUCCESS) {
            item(key = "success-result") {
                FarmSuccessResult(ui, jobs)
            }
        }

        if (ui.phase == FarmRunPhase.FAILED) {
            item(key = "failure-result") {
                FarmFailureResult(ui, failedJobs)
            }
        }

        ui.progress?.htmlUrl?.takeIf { it.isNotBlank() }?.let { logUrl ->
            item(key = "log") {
                OutlinedButton(
                    onClick = {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(logUrl)))
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("View Full Log")
                }
            }
        }

        if (ui.phase == FarmRunPhase.PREPARING || ui.phase == FarmRunPhase.RUNNING) {
            item(key = "cancel-boundary") {
                Text(
                    "Stop Test is not shown because the current Source Lab backend does not expose a cancel capability. The running workflow remains controlled by GitHub Actions.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        if (ui.phase == FarmRunPhase.SUCCESS || ui.phase == FarmRunPhase.FAILED) {
            item(key = "done") {
                Button(onClick = onClose, modifier = Modifier.fillMaxWidth()) {
                    Text("Back to Dashboard")
                }
            }
        }
    }
}

@Composable
private fun FarmRunStatusCard(
    ui: FarmRunUiState,
    elapsedSeconds: Long,
    completedJobs: Int,
    totalJobs: Int,
    progressFraction: Float,
    currentJob: MonitoredFarmJob?,
) {
    val status = when (ui.phase) {
        FarmRunPhase.PREPARING -> "Preparing" to SourceLabTone.ACCENT
        FarmRunPhase.RUNNING -> "Testing" to SourceLabTone.ACCENT
        FarmRunPhase.SUCCESS -> "Passed" to SourceLabTone.GOOD
        FarmRunPhase.FAILED -> "Failed" to SourceLabTone.ERROR
    }
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        when (ui.phase) {
                            FarmRunPhase.PREPARING -> "Preparing secure Owner run"
                            FarmRunPhase.RUNNING -> "Compatibility Farm is running"
                            FarmRunPhase.SUCCESS -> "Compatibility Farm completed"
                            FarmRunPhase.FAILED -> "Compatibility Farm stopped with an error"
                        },
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        ui.progress?.let { "Run #${it.runNumber} · ${formatElapsed(elapsedSeconds)}" }
                            ?: "Elapsed ${formatElapsed(elapsedSeconds)}",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                SourceLabStatusBadge(status.first, status.second)
            }

            if (ui.phase == FarmRunPhase.PREPARING || ui.phase == FarmRunPhase.RUNNING) {
                if (totalJobs > 0) {
                    LinearProgressIndicator(
                        progress = { progressFraction.coerceIn(0f, 1f) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Text(
                        "$completedJobs / $totalJobs workflow jobs completed",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                    Text(
                        "Waiting for GitHub Actions to expose the workflow jobs…",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                currentJob?.let {
                    Text("Current test: ${it.name}", fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
private fun FarmJobRow(job: MonitoredFarmJob) {
    val status = jobStatus(job)
    Card(colors = CardDefaults.cardColors(containerColor = SourceLabSurface)) {
        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(job.name, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    val completedSteps = job.steps.count { it.status == "completed" }
                    if (job.steps.isNotEmpty()) {
                        Text(
                            "$completedSteps / ${job.steps.size} steps completed",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                SourceLabStatusBadge(status.first, status.second)
            }
            val activeStep = job.steps.firstOrNull { it.status == "in_progress" }
            if (activeStep != null) {
                Text(
                    "Now: ${activeStep.name}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun FarmSuccessResult(ui: FarmRunUiState, jobs: List<MonitoredFarmJob>) {
    val snapshot = ui.snapshot
    val candidate = snapshot?.approvalCandidate
    val measurableJobs = jobs.filter { jobStatus(it).first != "N/A" }
    val passedJobs = measurableJobs.count { jobStatus(it).first == "PASS" }
    val passPercent = if (measurableJobs.isNotEmpty()) passedJobs * 100 / measurableJobs.size else null

    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Test Result", fontWeight = FontWeight.Bold)
                SourceLabStatusBadge("PASS", SourceLabTone.GOOD)
            }
            passPercent?.let {
                Text("Executed workflow checks passed: $it%", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }
            when {
                candidate != null -> {
                    SourceLabStatusBadge("Ready for Approval", SourceLabTone.GOOD)
                    Text(
                        "A real candidate is staged by the fail-closed Compatibility Farm gate and is waiting for Owner approval.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    candidate.providers.forEach { (provider, versions) ->
                        Surface(shape = RoundedCornerShape(10.dp), color = SourceLabSurface) {
                            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(providerDisplayName(provider), fontWeight = FontWeight.SemiBold)
                                Text("Current · ${shortRunRef(versions.current)}", fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
                                Text("Candidate · ${shortRunRef(versions.candidate)}", fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
                else -> {
                    SourceLabStatusBadge("No approval candidate", SourceLabTone.NEUTRAL)
                    Text(
                        "The Farm run succeeded but the live backend did not stage a candidate. No approval action is presented.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun FarmFailureResult(ui: FarmRunUiState, failedJobs: List<MonitoredFarmJob>) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Candidate / Farm Result", fontWeight = FontWeight.Bold)
                SourceLabStatusBadge("FAILED", SourceLabTone.ERROR)
            }
            Text(ui.error ?: "Compatibility Farm workflow failed.", color = MaterialTheme.colorScheme.error)
            if (failedJobs.isNotEmpty()) {
                Text("Failure summary", fontWeight = FontWeight.SemiBold)
                failedJobs.forEach { job ->
                    Text("• ${job.name}", style = MaterialTheme.typography.bodySmall)
                    job.steps.filter { stepStatus(it).first == "FAIL" }.forEach { step ->
                        Text(
                            "  ${step.name}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            } else {
                Text(
                    "No failed GitHub job detail was available. The backend error above is preserved without inventing a parser failure.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

internal fun jobStatus(job: MonitoredFarmJob): Pair<String, SourceLabTone> {
    if (job.status == "in_progress") return "TESTING" to SourceLabTone.ACCENT
    if (job.status in setOf("queued", "waiting", "pending", "requested")) return "WAITING" to SourceLabTone.NEUTRAL
    return when (job.conclusion?.lowercase()) {
        "success" -> "PASS" to SourceLabTone.GOOD
        "skipped", "neutral" -> "N/A" to SourceLabTone.NEUTRAL
        "failure", "cancelled", "timed_out", "action_required", "startup_failure" -> "FAIL" to SourceLabTone.ERROR
        else -> if (job.status == "completed") "N/A" to SourceLabTone.NEUTRAL else "WAITING" to SourceLabTone.NEUTRAL
    }
}

internal fun stepStatus(step: MonitoredFarmStep): Pair<String, SourceLabTone> {
    if (step.status == "in_progress") return "TESTING" to SourceLabTone.ACCENT
    if (step.status in setOf("queued", "waiting", "pending")) return "WAITING" to SourceLabTone.NEUTRAL
    return when (step.conclusion?.lowercase()) {
        "success" -> "PASS" to SourceLabTone.GOOD
        "skipped", "neutral" -> "N/A" to SourceLabTone.NEUTRAL
        "failure", "cancelled", "timed_out", "action_required", "startup_failure" -> "FAIL" to SourceLabTone.ERROR
        else -> if (step.status == "completed") "N/A" to SourceLabTone.NEUTRAL else "WAITING" to SourceLabTone.NEUTRAL
    }
}

private fun formatElapsed(seconds: Long): String {
    val minutes = seconds / 60L
    val remainder = seconds % 60L
    return "%02d:%02d".format(minutes, remainder)
}

private fun providerDisplayName(value: String): String = when (value.lowercase()) {
    "keiyoushi" -> "Keiyoushi"
    "uma" -> "UMA"
    "gekkoushi" -> "Gekkoushi"
    else -> value.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
}

private fun shortRunRef(value: String): String = if (value.length > 12) value.take(12) else value

private object FarmRunMonitor {
    private const val repository = "Noirero/Miyorare-Source-Packs"
    private const val apiBase = "https://api.github.com/repos/$repository"
    private const val workflow = "source-lab-run-farm.yml"

    fun latestOwnerRunId(token: String): Long? = listRuns(token)
        .firstOrNull { it.actorId == SourceLabAccessPolicy.ownerGithubUserId }
        ?.id

    fun findOwnerRunAfter(token: String, baselineRunId: Long): MonitoredFarmRun? {
        val run = listRuns(token).firstOrNull {
            it.actorId == SourceLabAccessPolicy.ownerGithubUserId && it.id > baselineRunId
        } ?: return null
        return loadRun(token, run.id)
    }

    fun loadRun(token: String, runId: Long): MonitoredFarmRun {
        val run = JSONObject(fetchText("$apiBase/actions/runs/$runId", token))
        val jobsPayload = JSONObject(fetchText("$apiBase/actions/runs/$runId/jobs?per_page=100", token))
        val jobsJson = jobsPayload.getJSONArray("jobs")
        val jobs = buildList {
            for (index in 0 until jobsJson.length()) {
                val job = jobsJson.getJSONObject(index)
                val stepsJson = job.optJSONArray("steps")
                val steps = buildList {
                    if (stepsJson != null) {
                        for (stepIndex in 0 until stepsJson.length()) {
                            val step = stepsJson.getJSONObject(stepIndex)
                            add(
                                MonitoredFarmStep(
                                    name = step.optString("name", "Step ${stepIndex + 1}"),
                                    status = step.optString("status", "unknown"),
                                    conclusion = step.optString("conclusion").takeIf { it.isNotBlank() && it != "null" },
                                ),
                            )
                        }
                    }
                }
                add(
                    MonitoredFarmJob(
                        id = job.getLong("id"),
                        name = job.optString("name", "Workflow job"),
                        status = job.optString("status", "unknown"),
                        conclusion = job.optString("conclusion").takeIf { it.isNotBlank() && it != "null" },
                        steps = steps,
                    ),
                )
            }
        }
        return MonitoredFarmRun(
            id = run.getLong("id"),
            runNumber = run.optInt("run_number"),
            status = run.optString("status", "unknown"),
            conclusion = run.optString("conclusion").takeIf { it.isNotBlank() && it != "null" },
            title = run.optString("display_title", "Source Lab Farm"),
            htmlUrl = run.optString("html_url"),
            jobs = jobs,
        )
    }

    private fun listRuns(token: String): List<RunListItem> {
        val payload = JSONObject(
            fetchText(
                "$apiBase/actions/workflows/$workflow/runs?event=workflow_dispatch&branch=main&per_page=20",
                token,
            ),
        )
        val runs = payload.getJSONArray("workflow_runs")
        return buildList {
            for (index in 0 until runs.length()) {
                val run = runs.getJSONObject(index)
                add(
                    RunListItem(
                        id = run.getLong("id"),
                        actorId = run.optJSONObject("actor")?.optLong("id", -1L) ?: -1L,
                    ),
                )
            }
        }
    }

    private fun fetchText(url: String, token: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10_000
            readTimeout = 20_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/${BuildConfig.VERSION_NAME}")
            useCaches = false
        }
        return try {
            val statusCode = connection.responseCode
            if (statusCode !in 200..299) error("HTTP $statusCode while reading Farm run progress")
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private data class RunListItem(
        val id: Long,
        val actorId: Long,
    )
}
