package com.noirero.miyorare.sourcelab

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.SecureRandom

internal data class BackendAuthorizationProof(
    val challenge: String,
    val workflowRunId: Long,
)

internal data class ApprovalWorkflowReceipt(
    val candidateSetId: String,
    val workflowRunId: Long,
)

private data class WorkflowRunState(
    val id: Long,
    val displayTitle: String,
    val status: String,
    val conclusion: String?,
    val actorId: Long,
    val headBranch: String,
    val event: String,
)

internal object GitHubControlPlaneClient {
    private const val apiBase = "https://api.github.com/repos/Noirero/Miyorare-Source-Packs"
    private const val backendAuthorizationWorkflow = "source-lab-backend-authorization.yml"
    private const val approveWorkflow = "source-lab-approve-candidate.yml"
    private const val controlRef = "main"
    private val hex64 = Regex("^[0-9a-f]{64}$")
    private val secureRandom = SecureRandom()

    suspend fun authorizeBackend(accessToken: String): BackendAuthorizationProof {
        val challenge = randomChallenge()
        val title = "Source Lab auth $challenge"
        withContext(Dispatchers.IO) {
            dispatchWorkflow(
                accessToken = accessToken,
                workflow = backendAuthorizationWorkflow,
                inputs = mapOf("challenge" to challenge),
            )
        }
        val run = awaitSuccessfulRun(accessToken, backendAuthorizationWorkflow, title)
        return BackendAuthorizationProof(challenge = challenge, workflowRunId = run.id)
    }

    suspend fun approveCandidate(
        accessToken: String,
        candidateSetId: String,
        farmEvidenceSha256: String,
        gateSha256: String,
        repairEvidenceSha256: String,
    ): ApprovalWorkflowReceipt {
        requireDigest(candidateSetId, "candidateSetId")
        requireDigest(farmEvidenceSha256, "farmEvidenceSha256")
        requireDigest(gateSha256, "gateSha256")
        requireDigest(repairEvidenceSha256, "repairEvidenceSha256")

        val title = "Source Lab approve $candidateSetId"
        withContext(Dispatchers.IO) {
            dispatchWorkflow(
                accessToken = accessToken,
                workflow = approveWorkflow,
                inputs = mapOf(
                    "candidate_set_id" to candidateSetId,
                    "farm_evidence_sha256" to farmEvidenceSha256,
                    "gate_sha256" to gateSha256,
                    "repair_evidence_sha256" to repairEvidenceSha256,
                ),
            )
        }
        val run = awaitSuccessfulRun(accessToken, approveWorkflow, title)
        return ApprovalWorkflowReceipt(candidateSetId = candidateSetId, workflowRunId = run.id)
    }

    private fun dispatchWorkflow(accessToken: String, workflow: String, inputs: Map<String, String>) {
        val url = "$apiBase/actions/workflows/${encodePathSegment(workflow)}/dispatches"
        val payload = JSONObject()
            .put("ref", controlRef)
            .put("inputs", JSONObject(inputs))
            .toString()
        val connection = open(url, "POST", accessToken).apply {
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        val errorBody = if (code in 200..299) "" else readBody(connection, success = false)
        connection.disconnect()
        if (code !in 200..299) {
            val message = parseMessage(errorBody)
            when (code) {
                403 -> error("GITHUB_ACTIONS_WRITE_REQUIRED: $message")
                404 -> error("GITHUB_WORKFLOW_NOT_ACCESSIBLE_404: $message")
                else -> error("GITHUB_WORKFLOW_DISPATCH_HTTP_$code: $message")
            }
        }
    }

    private suspend fun awaitSuccessfulRun(
        accessToken: String,
        workflow: String,
        expectedTitle: String,
    ): WorkflowRunState {
        repeat(60) {
            val runs = withContext(Dispatchers.IO) { listRecentRuns(accessToken, workflow) }
            val run = runs.firstOrNull { item ->
                item.displayTitle == expectedTitle &&
                    item.actorId == GitHubAppPublicConfig.ownerGithubUserId &&
                    item.headBranch == controlRef &&
                    item.event == "workflow_dispatch"
            }
            if (run != null) {
                if (run.status == "completed") {
                    if (run.conclusion == "success") return run
                    error("CONTROL_PLANE_RUN_${run.conclusion?.uppercase() ?: "FAILED"}: ${run.id}")
                }
            }
            delay(2_000L)
        }
        error("CONTROL_PLANE_RUN_TIMEOUT")
    }

    private fun listRecentRuns(accessToken: String, workflow: String): List<WorkflowRunState> {
        val url = "$apiBase/actions/workflows/${encodePathSegment(workflow)}/runs" +
            "?event=workflow_dispatch&branch=$controlRef&per_page=20"
        val connection = open(url, "GET", accessToken)
        val code = connection.responseCode
        val body = readBody(connection, success = code in 200..299)
        connection.disconnect()
        if (code !in 200..299) {
            val message = parseMessage(body)
            when (code) {
                403 -> error("GITHUB_ACTIONS_READ_REQUIRED: $message")
                404 -> error("GITHUB_WORKFLOW_NOT_ACCESSIBLE_404: $message")
                else -> error("GITHUB_WORKFLOW_RUNS_HTTP_$code: $message")
            }
        }

        val runs = JSONObject(body).optJSONArray("workflow_runs") ?: return emptyList()
        return buildList {
            for (index in 0 until runs.length()) {
                val run = runs.optJSONObject(index) ?: continue
                add(
                    WorkflowRunState(
                        id = run.optLong("id"),
                        displayTitle = run.optString("display_title"),
                        status = run.optString("status"),
                        conclusion = run.optString("conclusion").takeIf { it.isNotBlank() && it != "null" },
                        actorId = run.optJSONObject("actor")?.optLong("id") ?: -1L,
                        headBranch = run.optString("head_branch"),
                        event = run.optString("event"),
                    )
                )
            }
        }
    }

    private fun open(url: String, method: String, accessToken: String): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 15_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("Authorization", "Bearer $accessToken")
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab")
            useCaches = false
        }

    private fun readBody(connection: HttpURLConnection, success: Boolean): String =
        (if (success) connection.inputStream else connection.errorStream)
            ?.bufferedReader()
            ?.use { it.readText() }
            .orEmpty()

    private fun parseMessage(body: String): String = try {
        JSONObject(body).optString("message").ifBlank { body.ifBlank { "unknown GitHub error" } }
    } catch (_: Throwable) {
        body.ifBlank { "unknown GitHub error" }
    }

    private fun randomChallenge(): String {
        val bytes = ByteArray(32)
        secureRandom.nextBytes(bytes)
        return bytes.joinToString("") { "%02x".format(it) }
    }

    private fun requireDigest(value: String, name: String) {
        require(hex64.matches(value)) { "$name must be a lowercase SHA-256 digest" }
    }

    private fun encodePathSegment(value: String): String =
        URLEncoder.encode(value, Charsets.UTF_8.name()).replace("+", "%20")
}
