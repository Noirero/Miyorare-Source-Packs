package com.noirero.miyorare.sourcelab

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private sealed interface OwnerLoginV2State {
    data object Idle : OwnerLoginV2State
    data object Requesting : OwnerLoginV2State
    data class Waiting(val authorization: DeviceAuthorization, val pollDelaySeconds: Long) : OwnerLoginV2State
    data object AuthorizingBackend : OwnerLoginV2State
    data class Verified(
        val identity: GitHubIdentity,
        val repositoryPermission: String,
        val decision: AccessDecision,
        val backendRunId: Long,
    ) : OwnerLoginV2State
    data class Failed(val message: String) : OwnerLoginV2State
}

@Composable
internal fun OwnerLoginCardV2(onOwnerReady: () -> Unit) {
    var state by remember { mutableStateOf<OwnerLoginV2State>(OwnerLoginV2State.Idle) }
    val scope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current

    fun reset() {
        OwnerSessionStore.clear()
        state = OwnerLoginV2State.Idle
    }

    fun beginLogin() {
        OwnerSessionStore.clear()
        state = OwnerLoginV2State.Requesting
        scope.launch {
            state = try {
                val auth = withContext(Dispatchers.IO) { GitHubDeviceFlowClient.requestAuthorization() }
                OwnerLoginV2State.Waiting(auth, auth.intervalSeconds)
            } catch (error: Throwable) {
                OwnerLoginV2State.Failed(error.message ?: error.javaClass.simpleName)
            }
        }
    }

    val waiting = state as? OwnerLoginV2State.Waiting
    LaunchedEffect(waiting?.authorization?.deviceCode) {
        val active = waiting ?: return@LaunchedEffect
        val deadline = System.currentTimeMillis() + active.authorization.expiresInSeconds * 1000L
        var interval = active.pollDelaySeconds

        while (System.currentTimeMillis() < deadline) {
            delay(interval * 1000L)
            val result = try {
                withContext(Dispatchers.IO) { GitHubDeviceFlowClient.pollToken(active.authorization.deviceCode) }
            } catch (error: Throwable) {
                state = OwnerLoginV2State.Failed(error.message ?: error.javaClass.simpleName)
                return@LaunchedEffect
            }

            when (result) {
                is DeviceTokenPoll.Pending -> Unit
                is DeviceTokenPoll.SlowDown -> interval += result.extraDelaySeconds
                is DeviceTokenPoll.Expired -> {
                    state = OwnerLoginV2State.Failed("DEVICE_CODE_EXPIRED")
                    return@LaunchedEffect
                }
                is DeviceTokenPoll.Denied -> {
                    state = OwnerLoginV2State.Failed("DEVICE_AUTHORIZATION_DENIED")
                    return@LaunchedEffect
                }
                is DeviceTokenPoll.Failed -> {
                    state = OwnerLoginV2State.Failed(result.message)
                    return@LaunchedEffect
                }
                is DeviceTokenPoll.Success -> {
                    val ownerIdentity = try {
                        withContext(Dispatchers.IO) {
                            val identity = GitHubDeviceFlowClient.fetchIdentity(result.accessToken)
                            val permission = GitHubDeviceFlowClient.fetchRepositoryPermission(result.accessToken)
                            Pair(identity, permission)
                        }
                    } catch (error: Throwable) {
                        state = OwnerLoginV2State.Failed(error.message ?: error.javaClass.simpleName)
                        return@LaunchedEffect
                    }

                    val preBackendSession = OwnerAccessSession(
                        authenticated = true,
                        githubUserId = ownerIdentity.first.id,
                        githubAppId = GitHubAppPublicConfig.appId,
                        installationId = GitHubAppPublicConfig.installationId,
                        repository = GitHubAppPublicConfig.repository,
                        repositoryPermission = ownerIdentity.second,
                        backendAuthorized = false,
                    )
                    val preBackendDecision = SourceLabAccessPolicy.evaluate(preBackendSession)
                    if (preBackendDecision.reason != "BACKEND_AUTHORIZATION_REQUIRED") {
                        state = OwnerLoginV2State.Verified(
                            identity = ownerIdentity.first,
                            repositoryPermission = ownerIdentity.second,
                            decision = preBackendDecision,
                            backendRunId = 0L,
                        )
                        return@LaunchedEffect
                    }

                    state = OwnerLoginV2State.AuthorizingBackend
                    val backend = try {
                        GitHubControlPlaneClient.authorizeBackend(result.accessToken)
                    } catch (error: Throwable) {
                        state = OwnerLoginV2State.Failed(error.message ?: error.javaClass.simpleName)
                        return@LaunchedEffect
                    }
                    val authorizedSession = preBackendSession.copy(backendAuthorized = true)
                    val finalDecision = SourceLabAccessPolicy.evaluate(authorizedSession)
                    if (!finalDecision.canControl) {
                        state = OwnerLoginV2State.Failed(finalDecision.reason)
                        return@LaunchedEffect
                    }

                    OwnerSessionStore.set(
                        OwnerRuntimeSession(
                            accessToken = result.accessToken,
                            access = authorizedSession,
                            backendAuthorizationRunId = backend.workflowRunId,
                        )
                    )
                    state = OwnerLoginV2State.Verified(
                        identity = ownerIdentity.first,
                        repositoryPermission = ownerIdentity.second,
                        decision = finalDecision,
                        backendRunId = backend.workflowRunId,
                    )
                    return@LaunchedEffect
                }
            }
        }
        state = OwnerLoginV2State.Failed("DEVICE_CODE_EXPIRED")
    }

    Card {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.owner_mode), fontWeight = FontWeight.Bold)
            when (val current = state) {
                OwnerLoginV2State.Idle -> {
                    Text(stringResource(R.string.owner_mode_public_viewer))
                    Button(onClick = ::beginLogin, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.sign_in_as_owner))
                    }
                }
                OwnerLoginV2State.Requesting -> Text(stringResource(R.string.owner_login_requesting))
                is OwnerLoginV2State.Waiting -> {
                    Text(stringResource(R.string.owner_login_code_label))
                    Text(current.authorization.userCode, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                    Text(stringResource(R.string.owner_login_waiting))
                    OutlinedButton(
                        onClick = { uriHandler.openUri(current.authorization.verificationUri) },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text(stringResource(R.string.open_github)) }
                }
                OwnerLoginV2State.AuthorizingBackend -> {
                    Text(stringResource(R.string.owner_backend_authorizing), fontWeight = FontWeight.Bold)
                    Text(stringResource(R.string.owner_backend_authorizing_supporting))
                }
                is OwnerLoginV2State.Verified -> {
                    if (current.decision.canControl) {
                        Text(stringResource(R.string.owner_identity_verified, current.identity.login))
                        Text(stringResource(R.string.owner_repository_permission, current.repositoryPermission))
                        Text(stringResource(R.string.owner_backend_verified, current.backendRunId))
                        Text(stringResource(R.string.owner_gate_result, current.decision.reason))
                        Button(onClick = onOwnerReady, modifier = Modifier.fillMaxWidth()) {
                            Text(stringResource(R.string.continue_as_owner))
                        }
                    } else {
                        Text(stringResource(R.string.non_owner_identity, current.identity.login))
                        Text(stringResource(R.string.owner_gate_result, current.decision.reason))
                    }
                    OutlinedButton(onClick = ::reset, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.reset_owner_login))
                    }
                }
                is OwnerLoginV2State.Failed -> {
                    Text(stringResource(R.string.owner_login_failed), color = MaterialTheme.colorScheme.error)
                    Text(current.message, color = MaterialTheme.colorScheme.error)
                    when {
                        current.message.startsWith("GITHUB_DEVICE_FLOW_404") ->
                            Text(stringResource(R.string.owner_device_flow_hint))
                        current.message.startsWith("GITHUB_ACTIONS_WRITE_REQUIRED") ||
                            current.message.startsWith("GITHUB_ACTIONS_READ_REQUIRED") ||
                            current.message.startsWith("GITHUB_WORKFLOW_NOT_ACCESSIBLE_404") ->
                            Text(stringResource(R.string.owner_actions_permission_hint))
                    }
                    OutlinedButton(onClick = ::beginLogin, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.retry))
                    }
                }
            }
        }
    }
}
