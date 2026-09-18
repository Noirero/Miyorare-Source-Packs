package com.noirero.miyorare.sourcelab

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets
import java.security.SecureRandom

internal data class SourceLabActionAvailability(
    val action: SourceLabControlAction,
    val available: Boolean,
    val reason: String,
    val prerequisiteRunId: Long? = null,
)

internal data class SourceLabResolvedControlState(
    val session: OwnerAccessSession,
    val approvalRunId: Long?,
    val signingRunId: Long?,
    val publishRunId: Long?,
    val actions: Map<SourceLabControlAction, SourceLabActionAvailability>,
)

internal data class SourceLabActionResult(
    val action: SourceLabControlAction,
    val runId: Long,
    val conclusion: String,
)

internal data class SourceLabApprovalPipelineResult(
    val approvalRunId: Long,
    val promotionRunId: Long,
    val signingRunId: Long,
    val publishRunId: Long,
)

internal class SourceLabControlException(
    val reason: String,
) : RuntimeException(reason)

internal object SourceLabControlClient {
    private const val repository = SourceLabAccessPolicy.repository
    private const val apiBase = "https://api.github.com/repos/$repository"
    private const val mainRef = "main"
    private const val pollIntervalMs = 5_000L
    private const val maxPolls = 1_500

    suspend fun resolveOwnerSession(context: Context): OwnerAccessSession = withContext(Dispatchers.IO) {
        refreshOwnerContext(context).session
    }

    suspend fun resolveState(
        context: Context,
        snapshot: LiveFarmSnapshot,
    ): SourceLabResolvedControlState = withContext(Dispatchers.IO) {
        val owner = refreshOwnerContext(context)
        val candidateId = snapshot.approvalCandidate?.candidateSetId
        val promotionId = snapshot.lastPromotion?.candidateSetId

        val approvalRunId = candidateId?.let {
            findSuccessfulRun(owner.token, "source-lab-approve-candidate.yml", "Source Lab approve $it")
        }
        val signingRunId = promotionId?.let {
            findSuccessfulRun(owner.token, "source-lab-sign-candidate.yml", "Source Lab sign $it")
        }
        val publishRunId = promotionId?.let {
            findSuccessfulRun(owner.token, "source-lab-publish-candidate.yml", "Source Lab publish $it")
        }

        SourceLabResolvedControlState(
            session = owner.session,
            approvalRunId = approvalRunId,
            signingRunId = signingRunId,
            publishRunId = publishRunId,
            actions = buildAvailability(
                session = owner.session,
                snapshot = snapshot,
                approvalRunId = approvalRunId,
                signingRunId = signingRunId,
                publishRunId = publishRunId,
            ),
        )
    }

    suspend fun approveAndPublish(
        context: Context,
        snapshot: LiveFarmSnapshot,
    ): SourceLabApprovalPipelineResult = withContext(Dispatchers.IO) {
        val approval = execute(context, snapshot, SourceLabControlAction.APPROVE)
        var current = SourceLabRepository.loadSnapshot()
        val promotion = execute(context, current, SourceLabControlAction.PROMOTE)
        current = SourceLabRepository.loadSnapshot()
        val signing = execute(context, current, SourceLabControlAction.SIGN)
        current = SourceLabRepository.loadSnapshot()
        val publish = execute(context, current, SourceLabControlAction.PUBLISH)
        SourceLabApprovalPipelineResult(
            approvalRunId = approval.runId,
            promotionRunId = promotion.runId,
            signingRunId = signing.runId,
            publishRunId = publish.runId,
        )
    }

    suspend fun addToFarm(
        context: Context,
        source: InventorySource,
        inventory: SourceInventorySnapshot,
        farm: FarmInventorySnapshot,
    ): SourceLabActionResult = withContext(Dispatchers.IO) {
        val owner = refreshOwnerContext(context)
        if (!SourceLabAccessPolicy.canPerform(SourceLabControlAction.ADD_TO_FARM, owner.session)) {
            throw SourceLabControlException("BACKEND_CAPABILITY_ADD_TO_FARM_UNAVAILABLE")
        }
        if (source.needsAttention) throw SourceLabControlException("SOURCE_IDENTITY_NEEDS_ATTENTION")
        if (farm.sources.any { it.canonicalId == source.canonicalId }) {
            throw SourceLabControlException("SOURCE_ALREADY_ENROLLED")
        }
        if (!inventory.branchCommit.matches(Regex("^[0-9a-f]{40}$"))) {
            throw SourceLabControlException("INVENTORY_COMMIT_INVALID")
        }
        if (!farm.branchCommit.matches(Regex("^[0-9a-f]{40}$"))) {
            throw SourceLabControlException("FOUNDATION_COMMIT_INVALID")
        }
        val request = ControlRequest(
            workflow = "source-lab-add-to-farm.yml",
            title = "Source Lab add-to-farm ${source.canonicalId}",
            inputs = mapOf(
                "canonical_id" to source.canonicalId,
                "inventory_commit" to inventory.branchCommit,
                "foundation_commit" to farm.branchCommit,
            ),
        )
        dispatchAndWait(owner.token, SourceLabControlAction.ADD_TO_FARM, request)
    }

    suspend fun execute(
        context: Context,
        snapshot: LiveFarmSnapshot,
        action: SourceLabControlAction,
    ): SourceLabActionResult = withContext(Dispatchers.IO) {
        if (action == SourceLabControlAction.ADD_TO_FARM) {
            throw SourceLabControlException("SOURCE_DETAIL_REQUIRED")
        }
        val owner = refreshOwnerContext(context)
        val candidateId = snapshot.approvalCandidate?.candidateSetId
        val promotionId = snapshot.lastPromotion?.candidateSetId
        val approvalRunId = candidateId?.let {
            findSuccessfulRun(owner.token, "source-lab-approve-candidate.yml", "Source Lab approve $it")
        }
        val signingRunId = promotionId?.let {
            findSuccessfulRun(owner.token, "source-lab-sign-candidate.yml", "Source Lab sign $it")
        }
        val publishRunId = promotionId?.let {
            findSuccessfulRun(owner.token, "source-lab-publish-candidate.yml", "Source Lab publish $it")
        }
        val availability = buildAvailability(
            session = owner.session,
            snapshot = snapshot,
            approvalRunId = approvalRunId,
            signingRunId = signingRunId,
            publishRunId = publishRunId,
        ).getValue(action)
        if (!availability.available) throw SourceLabControlException(availability.reason)

        val request = when (action) {
            SourceLabControlAction.RUN_FARM -> {
                val requestId = randomHex(16)
                ControlRequest(
                    workflow = "source-lab-run-farm.yml",
                    title = "Source Lab run farm $requestId",
                    inputs = mapOf("request_id" to requestId),
                )
            }
            SourceLabControlAction.APPROVE -> {
                val candidate = snapshot.approvalCandidate
                    ?: throw SourceLabControlException("NO_LIVE_APPROVAL_CANDIDATE")
                val evidence = candidate.evidenceBinding
                ControlRequest(
                    workflow = "source-lab-approve-candidate.yml",
                    title = "Source Lab approve ${candidate.candidateSetId}",
                    inputs = mapOf(
                        "candidate_set_id" to candidate.candidateSetId,
                        "farm_evidence_sha256" to evidence.farmEvidenceSha256,
                        "gate_sha256" to evidence.gateSha256,
                        "repair_evidence_sha256" to evidence.repairEvidenceSha256,
                    ),
                )
            }
            SourceLabControlAction.PROMOTE -> {
                val candidate = snapshot.approvalCandidate
                    ?: throw SourceLabControlException("NO_LIVE_APPROVAL_CANDIDATE")
                val runId = approvalRunId
                    ?: throw SourceLabControlException("APPROVAL_RECEIPT_REQUIRED")
                ControlRequest(
                    workflow = "source-lab-promote-candidate.yml",
                    title = "Source Lab promote ${candidate.candidateSetId}",
                    inputs = mapOf(
                        "candidate_set_id" to candidate.candidateSetId,
                        "approval_run_id" to runId.toString(),
                    ),
                )
            }
            SourceLabControlAction.SIGN -> {
                val promotion = snapshot.lastPromotion
                    ?: throw SourceLabControlException("PROMOTION_REQUIRED")
                ControlRequest(
                    workflow = "source-lab-sign-candidate.yml",
                    title = "Source Lab sign ${promotion.candidateSetId}",
                    inputs = mapOf(
                        "candidate_set_id" to promotion.candidateSetId,
                        "promotion_run_id" to promotion.promotionRunId.toString(),
                    ),
                )
            }
            SourceLabControlAction.PUBLISH -> {
                val promotion = snapshot.lastPromotion
                    ?: throw SourceLabControlException("PROMOTION_REQUIRED")
                val runId = signingRunId
                    ?: throw SourceLabControlException("SIGNING_ATTESTATION_REQUIRED")
                ControlRequest(
                    workflow = "source-lab-publish-candidate.yml",
                    title = "Source Lab publish ${promotion.candidateSetId}",
                    inputs = mapOf(
                        "candidate_set_id" to promotion.candidateSetId,
                        "signing_run_id" to runId.toString(),
                    ),
                )
            }
            SourceLabControlAction.ADD_TO_FARM -> throw SourceLabControlException("SOURCE_DETAIL_REQUIRED")
            SourceLabControlAction.APPROVE_READY_SOURCES -> ControlRequest(
                workflow = "source-lab-approve-ready-sources.yml",
                title = "Source Lab approve ready sources",
                inputs = emptyMap(),
            )
        }
        dispatchAndWait(owner.token, action, request)
    }

    internal fun buildAvailability(
        session: OwnerAccessSession,
        snapshot: LiveFarmSnapshot,
        approvalRunId: Long?,
        signingRunId: Long?,
        publishRunId: Long?,
    ): Map<SourceLabControlAction, SourceLabActionAvailability> {
        val candidate = snapshot.approvalCandidate
        val promotion = snapshot.lastPromotion
        val publishedCurrentPromotion =
            promotion != null && snapshot.lastPublish?.candidateSetId == promotion.candidateSetId

        fun capability(action: SourceLabControlAction): String? =
            if (SourceLabAccessPolicy.canPerform(action, session)) null
            else "BACKEND_CAPABILITY_${action.name}_UNAVAILABLE"

        val runFarmReason = capability(SourceLabControlAction.RUN_FARM)
            ?: when {
                candidate != null -> "RESOLVE_LIVE_CANDIDATE_FIRST"
                promotion != null && !publishedCurrentPromotion -> "FINISH_SIGN_AND_PUBLISH_FIRST"
                else -> "AVAILABLE"
            }
        val approveReason = capability(SourceLabControlAction.APPROVE)
            ?: when {
                candidate == null -> "NO_LIVE_APPROVAL_CANDIDATE"
                candidate.state != "WAITING_FOR_APPROVAL" -> "CANDIDATE_NOT_WAITING_FOR_APPROVAL"
                candidate.publishEligible -> "CANDIDATE_ALREADY_PUBLISH_ELIGIBLE_REJECTED"
                approvalRunId != null -> "ALREADY_APPROVED_PIPELINE_CAN_RESUME_MANUALLY"
                else -> "AVAILABLE"
            }
        val promoteReason = capability(SourceLabControlAction.PROMOTE)
            ?: when {
                candidate == null -> "NO_LIVE_APPROVAL_CANDIDATE"
                candidate.state != "WAITING_FOR_APPROVAL" -> "CANDIDATE_NOT_WAITING_FOR_APPROVAL"
                approvalRunId == null -> "APPROVAL_RECEIPT_REQUIRED"
                else -> "AVAILABLE"
            }
        val signReason = capability(SourceLabControlAction.SIGN)
            ?: when {
                promotion == null -> "PROMOTION_REQUIRED"
                publishedCurrentPromotion -> "ALREADY_PUBLISHED"
                signingRunId != null -> "ALREADY_SIGNED_USE_PUBLISH"
                else -> "AVAILABLE"
            }
        val publishReason = capability(SourceLabControlAction.PUBLISH)
            ?: when {
                promotion == null -> "PROMOTION_REQUIRED"
                publishedCurrentPromotion || publishRunId != null -> "ALREADY_PUBLISHED"
                signingRunId == null -> "SIGNING_ATTESTATION_REQUIRED"
                else -> "AVAILABLE"
            }
        val addToFarmReason = capability(SourceLabControlAction.ADD_TO_FARM) ?: "SOURCE_DETAIL_REQUIRED"
        val approveReadySourcesReason = capability(SourceLabControlAction.APPROVE_READY_SOURCES)
            ?: when {
                candidate != null -> "PROVIDER_APPROVAL_PIPELINE_BUSY"
                promotion != null && !publishedCurrentPromotion -> "PROVIDER_PUBLISH_PIPELINE_BUSY"
                snapshot.pendingWorker == null -> "PENDING_WORKER_STATE_UNAVAILABLE"
                snapshot.pendingWorker.readyCount < 1 -> "NO_READY_SOURCE_ONBOARDING"
                else -> "AVAILABLE"
            }

        return mapOf(
            SourceLabControlAction.RUN_FARM to availability(SourceLabControlAction.RUN_FARM, runFarmReason),
            SourceLabControlAction.APPROVE to availability(SourceLabControlAction.APPROVE, approveReason),
            SourceLabControlAction.PROMOTE to availability(
                SourceLabControlAction.PROMOTE,
                promoteReason,
                approvalRunId,
            ),
            SourceLabControlAction.SIGN to availability(
                SourceLabControlAction.SIGN,
                signReason,
                promotion?.promotionRunId,
            ),
            SourceLabControlAction.PUBLISH to availability(
                SourceLabControlAction.PUBLISH,
                publishReason,
                signingRunId,
            ),
            SourceLabControlAction.ADD_TO_FARM to availability(
                SourceLabControlAction.ADD_TO_FARM,
                addToFarmReason,
            ),
            SourceLabControlAction.APPROVE_READY_SOURCES to availability(
                SourceLabControlAction.APPROVE_READY_SOURCES,
                approveReadySourcesReason,
            ),
        )
    }

    private fun availability(
        action: SourceLabControlAction,
        reason: String,
        prerequisiteRunId: Long? = null,
    ) = SourceLabActionAvailability(
        action = action,
        available = reason == "AVAILABLE",
        reason = reason,
        prerequisiteRunId = prerequisiteRunId,
    )

    private suspend fun refreshOwnerContext(context: Context): OwnerContext {
        val stored = GitHubOwnerCredentialVault.load(context)
            ?: throw SourceLabControlException("OWNER_CREDENTIAL_REQUIRED")
        val identity = try {
            GitHubOwnerAuthentication.restoreOwnerLogin(
                GitHubOwnerAuthentication.resolveClientId(),
                stored,
            )
        } catch (error: GitHubOwnerAuthenticationException) {
            throw SourceLabControlException(error.reason)
        }
        GitHubOwnerCredentialVault.save(context, identity.credential)

        val proof = SourceLabBackendAuthorization.authorize(identity.accessToken)
        if (!proof.authorized) throw SourceLabControlException(proof.reason)
        val baseSession = proof.applyTo(identity.session)
        val capabilities = try {
            SourceLabBackendCapabilityReader.read(identity.accessToken, proof)
        } catch (error: Throwable) {
            throw SourceLabControlException(error.message ?: "BACKEND_CAPABILITY_PROOF_INVALID")
        }
        val session = baseSession.copy(backendCapabilities = capabilities)
        val decision = SourceLabAccessPolicy.evaluate(session)
        if (!decision.canControl) throw SourceLabControlException(decision.reason)
        SourceLabOwnerSessionStore.set(session)
        return OwnerContext(identity.accessToken, session)
    }

    private fun dispatchAndWait(
        token: String,
        action: SourceLabControlAction,
        request: ControlRequest,
    ): SourceLabActionResult {
        val before = findLatestRun(token, request.workflow, request.title)?.id ?: 0L
        val inputs = JSONObject()
        request.inputs.forEach { (key, value) -> inputs.put(key, value) }
        val body = JSONObject()
            .put("ref", mainRef)
            .put("inputs", inputs)
            .toString()
        githubRequest(
            url = "$apiBase/actions/workflows/${request.workflow}/dispatches",
            token = token,
            method = "POST",
            body = body,
            expected = setOf(204),
        )

        var run: ControlRun? = null
        for (attempt in 0 until 90) {
            val candidate = findLatestRun(token, request.workflow, request.title)
            if (candidate != null && candidate.id > before) {
                run = candidate
                break
            }
            Thread.sleep(2_000L)
        }
        var current = run ?: throw SourceLabControlException("CONTROL_WORKFLOW_RUN_NOT_FOUND")
        repeat(maxPolls) {
            current = fetchRun(token, current.id)
            if (current.status == "completed") {
                if (current.conclusion != "success") {
                    throw SourceLabControlException(
                        "${action.name}_WORKFLOW_${current.conclusion.uppercase()}",
                    )
                }
                return SourceLabActionResult(action, current.id, current.conclusion)
            }
            Thread.sleep(pollIntervalMs)
        }
        throw SourceLabControlException("${action.name}_WORKFLOW_TIMEOUT")
    }

    private fun findSuccessfulRun(token: String, workflow: String, title: String): Long? {
        val payload = JSONObject(
            githubRequest(
                "$apiBase/actions/workflows/$workflow/runs?event=workflow_dispatch&branch=$mainRef&per_page=50",
                token,
            ).body,
        )
        val runs = payload.getJSONArray("workflow_runs")
        for (index in 0 until runs.length()) {
            val run = runs.getJSONObject(index)
            if (run.optString("display_title") != title) continue
            if (run.optJSONObject("actor")?.optLong("id", -1L) != SourceLabAccessPolicy.ownerGithubUserId) continue
            if (run.optString("status") == "completed" && run.optString("conclusion") == "success") {
                return run.getLong("id")
            }
        }
        return null
    }

    private fun findLatestRun(token: String, workflow: String, title: String): ControlRun? {
        val payload = JSONObject(
            githubRequest(
                "$apiBase/actions/workflows/$workflow/runs?event=workflow_dispatch&branch=$mainRef&per_page=30",
                token,
            ).body,
        )
        val runs = payload.getJSONArray("workflow_runs")
        for (index in 0 until runs.length()) {
            val run = runs.getJSONObject(index)
            if (run.optString("display_title") != title) continue
            if (run.optJSONObject("actor")?.optLong("id", -1L) != SourceLabAccessPolicy.ownerGithubUserId) continue
            return run.toControlRun()
        }
        return null
    }

    private fun fetchRun(token: String, runId: Long): ControlRun =
        JSONObject(githubRequest("$apiBase/actions/runs/$runId", token).body).toControlRun()

    private fun JSONObject.toControlRun() = ControlRun(
        id = getLong("id"),
        status = optString("status", "unknown"),
        conclusion = optString("conclusion", "").ifBlank { "unknown" },
    )

    private fun githubRequest(
        url: String,
        token: String,
        method: String = "GET",
        body: String? = null,
        expected: Set<Int> = (200..299).toSet(),
    ): HttpResult {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 10_000
            readTimeout = 20_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/${BuildConfig.VERSION_NAME}")
            useCaches = false
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        return try {
            if (body != null) {
                connection.outputStream.use { it.write(body.toByteArray(StandardCharsets.UTF_8)) }
            }
            val code = connection.responseCode
            if (code !in expected) throw SourceLabControlException("GITHUB_CONTROL_HTTP_$code")
            val response = if (code == 204) "" else connection.inputStream.bufferedReader().use { it.readText() }
            HttpResult(code, response)
        } finally {
            connection.disconnect()
        }
    }

    private fun randomHex(bytes: Int): String {
        val data = ByteArray(bytes)
        SecureRandom().nextBytes(data)
        return data.joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private data class OwnerContext(val token: String, val session: OwnerAccessSession)
    private data class ControlRequest(
        val workflow: String,
        val title: String,
        val inputs: Map<String, String>,
    )
    private data class ControlRun(val id: Long, val status: String, val conclusion: String)
    private data class HttpResult(val statusCode: Int, val body: String)
}
