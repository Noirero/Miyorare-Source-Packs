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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
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
                OwnerControlScreen(
                    onOpenDashboard = {
                        startActivity(Intent(this, LocalizedMainActivity::class.java))
                    },
                    onLogout = {
                        OwnerSessionStore.clear()
                        finish()
                    },
                )
            }
        }
    }
}

private sealed interface OwnerSnapshotState {
    data object Loading : OwnerSnapshotState
    data class Ready(val snapshot: LiveFarmSnapshot) : OwnerSnapshotState
    data class Failed(val message: String) : OwnerSnapshotState
}

private sealed interface OwnerApprovalState {
    data object Idle : OwnerApprovalState
    data object Running : OwnerApprovalState
    data class Succeeded(val runId: Long, val candidateSetId: String) : OwnerApprovalState
    data class Failed(val message: String) : OwnerApprovalState
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
private fun OwnerControlScreen(
    onOpenDashboard: () -> Unit,
    onLogout: () -> Unit,
) {
    val owner = remember { OwnerSessionStore.get() }
    val accessDecision = remember(owner) { SourceLabAccessPolicy.evaluate(owner?.access) }
    val canApprove = remember(owner) {
        owner != null && SourceLabAccessPolicy.canPerform(SourceLabControlAction.APPROVE, owner.access)
    }
    var refreshKey by remember { mutableIntStateOf(0) }
    var snapshotState by remember { mutableStateOf<OwnerSnapshotState>(OwnerSnapshotState.Loading) }
    var approvalState by remember { mutableStateOf<OwnerApprovalState>(OwnerApprovalState.Idle) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(refreshKey, canApprove) {
        if (!canApprove) return@LaunchedEffect
        snapshotState = OwnerSnapshotState.Loading
        snapshotState = try {
            OwnerSnapshotState.Ready(withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() })
        } catch (error: Throwable) {
            OwnerSnapshotState.Failed(error.message ?: error.javaClass.simpleName)
        }
    }

    val snapshot = (snapshotState as? OwnerSnapshotState.Ready)?.snapshot
    val candidate = snapshot?.approvalCandidate
    val approvalCompletedForCurrent = (approvalState as? OwnerApprovalState.Succeeded)
        ?.candidateSetId == candidate?.candidateSetId

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Text(
                stringResource(R.string.owner_control_title),
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                stringResource(R.string.owner_control_subtitle),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (owner == null) {
                        Text(stringResource(R.string.owner_session_missing), color = MaterialTheme.colorScheme.error)
                    } else if (!accessDecision.canControl) {
                        Text(
                            stringResource(R.string.owner_session_denied, accessDecision.reason),
                            color = MaterialTheme.colorScheme.error,
                        )
                    } else {
                        Text(
                            stringResource(R.string.owner_session_active, owner.backendAuthorizationRunId),
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.tertiary,
                        )
                        Text("GitHub user ${owner.access.githubUserId} · ${owner.access.repositoryPermission}")
                    }
                }
            }
        }

        when (val current = snapshotState) {
            OwnerSnapshotState.Loading -> if (canApprove) {
                item {
                    Card {
                        Row(
                            Modifier.fillMaxWidth().padding(16.dp),
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            CircularProgressIndicator()
                            Text(stringResource(R.string.owner_candidate_loading))
                        }
                    }
                }
            }
            is OwnerSnapshotState.Failed -> item {
                Card {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            stringResource(R.string.owner_candidate_load_failed, current.message),
                            color = MaterialTheme.colorScheme.error,
                        )
                        OutlinedButton(onClick = { refreshKey++ }, modifier = Modifier.fillMaxWidth()) {
                            Text(stringResource(R.string.owner_candidate_refresh))
                        }
                    }
                }
            }
            is OwnerSnapshotState.Ready -> {
                if (candidate == null) {
                    item {
                        Card {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text(stringResource(R.string.owner_candidate_no_waiting), fontWeight = FontWeight.Bold)
                                Text(
                                    stringResource(R.string.owner_candidate_no_waiting_supporting),
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                OutlinedButton(onClick = { refreshKey++ }, modifier = Modifier.fillMaxWidth()) {
                                    Text(stringResource(R.string.owner_candidate_refresh))
                                }
                            }
                        }
                    }
                } else {
                    item {
                        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text(stringResource(R.string.owner_candidate_title), fontWeight = FontWeight.Bold)
                                Text(stringResource(R.string.owner_candidate_provider_count, candidate.providers.size))
                                DigestText(stringResource(R.string.candidate_set_id_label, candidate.candidateSetId), candidate.candidateSetId)
                                Text(
                                    stringResource(R.string.approval_ready_supporting),
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }

                    items(candidate.providers, key = { it.id }) { provider ->
                        Card {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                                Text(provider.id.prettyProviderNameOwner(), fontWeight = FontWeight.Bold)
                                Text(stringResource(R.string.owner_expected_lkg))
                                MonospaceValue(provider.current)
                                Text(stringResource(R.string.owner_candidate_sha))
                                MonospaceValue(provider.candidate)
                            }
                        }
                    }

                    item {
                        Card {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                DigestText(stringResource(R.string.owner_farm_evidence_digest), candidate.evidence.farmEvidenceSha256)
                                DigestText(stringResource(R.string.owner_gate_evidence_digest), candidate.evidence.gateSha256)
                                DigestText(stringResource(R.string.owner_repair_evidence_digest), candidate.evidence.repairEvidenceSha256)
                                Text(stringResource(R.string.owner_repair_evidence_count, candidate.evidence.repairEvidenceCount))
                            }
                        }
                    }

                    item {
                        Card {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                Text(stringResource(R.string.owner_approve_warning), fontWeight = FontWeight.Bold)
                                Text(
                                    stringResource(R.string.owner_control_fail_closed),
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                when (val approval = approvalState) {
                                    OwnerApprovalState.Idle -> Unit
                                    OwnerApprovalState.Running -> Text(stringResource(R.string.owner_approval_running))
                                    is OwnerApprovalState.Succeeded -> {
                                        Text(
                                            stringResource(R.string.owner_approval_done, approval.runId),
                                            color = MaterialTheme.colorScheme.tertiary,
                                            fontWeight = FontWeight.Bold,
                                        )
                                        Text(stringResource(R.string.owner_approval_done_supporting))
                                    }
                                    is OwnerApprovalState.Failed -> Text(
                                        stringResource(R.string.approval_failed, approval.message),
                                        color = MaterialTheme.colorScheme.error,
                                    )
                                }

                                Button(
                                    onClick = {
                                        val activeOwner = owner ?: return@Button
                                        val exact = candidate
                                        approvalState = OwnerApprovalState.Running
                                        scope.launch {
                                            approvalState = try {
                                                val receipt = GitHubControlPlaneClient.approveCandidate(
                                                    accessToken = activeOwner.accessToken,
                                                    candidateSetId = exact.candidateSetId,
                                                    farmEvidenceSha256 = exact.evidence.farmEvidenceSha256,
                                                    gateSha256 = exact.evidence.gateSha256,
                                                    repairEvidenceSha256 = exact.evidence.repairEvidenceSha256,
                                                )
                                                OwnerApprovalState.Succeeded(
                                                    runId = receipt.workflowRunId,
                                                    candidateSetId = receipt.candidateSetId,
                                                )
                                            } catch (error: Throwable) {
                                                OwnerApprovalState.Failed(error.message ?: error.javaClass.simpleName)
                                            }
                                        }
                                    },
                                    enabled = canApprove &&
                                        approvalState !is OwnerApprovalState.Running &&
                                        !approvalCompletedForCurrent,
                                    modifier = Modifier.fillMaxWidth(),
                                ) {
                                    Text(
                                        if (approvalState is OwnerApprovalState.Failed) {
                                            stringResource(R.string.owner_approval_retry)
                                        } else {
                                            stringResource(R.string.owner_approve_button)
                                        }
                                    )
                                }
                                Text(
                                    stringResource(R.string.publish_remains_blocked),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
        }

        item {
            Spacer(Modifier.height(4.dp))
            Button(onClick = onOpenDashboard, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.owner_open_dashboard))
            }
            Spacer(Modifier.height(8.dp))
            OutlinedButton(onClick = onLogout, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.owner_logout))
            }
        }
    }
}

@Composable
private fun DigestText(label: String, value: String) {
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(label, fontWeight = FontWeight.SemiBold)
        MonospaceValue(value)
    }
}

@Composable
private fun MonospaceValue(value: String) {
    Text(
        text = value,
        style = MaterialTheme.typography.bodySmall,
        fontFamily = FontFamily.Monospace,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

private fun String.prettyProviderNameOwner(): String = when (lowercase()) {
    "keiyoushi" -> "Keiyoushi"
    "gekkoushi" -> "Gekkoushi"
    "uma" -> "UMA"
    else -> this
}
