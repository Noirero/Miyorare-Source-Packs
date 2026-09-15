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

private sealed interface OwnerLoginUiState {
    data object Idle : OwnerLoginUiState
    data object Requesting : OwnerLoginUiState
    data class Waiting(
        val authorization: DeviceAuthorization,
        val pollDelaySeconds: Long,
    ) : OwnerLoginUiState
    data class Verified(
        val identity: GitHubIdentity,
        val expectedOwner: Boolean,
    ) : OwnerLoginUiState
    data class Failed(val message: String) : OwnerLoginUiState
}

@Composable
internal fun OwnerLoginCard() {
    var state by remember { mutableStateOf<OwnerLoginUiState>(OwnerLoginUiState.Idle) }
    val scope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current

    fun beginLogin() {
        state = OwnerLoginUiState.Requesting
        scope.launch {
            state = try {
                val auth = withContext(Dispatchers.IO) { GitHubDeviceFlowClient.requestAuthorization() }
                OwnerLoginUiState.Waiting(auth, auth.intervalSeconds)
            } catch (error: Throwable) {
                OwnerLoginUiState.Failed(error.message ?: error.javaClass.simpleName)
            }
        }
    }

    val waiting = state as? OwnerLoginUiState.Waiting
    LaunchedEffect(waiting?.authorization?.deviceCode) {
        var active = waiting ?: return@LaunchedEffect
        val deadline = System.currentTimeMillis() + active.authorization.expiresInSeconds * 1000L
        var interval = active.pollDelaySeconds

        while (System.currentTimeMillis() < deadline) {
            delay(interval * 1000L)
            val result = try {
                withContext(Dispatchers.IO) {
                    GitHubDeviceFlowClient.pollToken(active.authorization.deviceCode)
                }
            } catch (error: Throwable) {
                state = OwnerLoginUiState.Failed(error.message ?: error.javaClass.simpleName)
                return@LaunchedEffect
            }

            when (result) {
                is DeviceTokenPoll.Pending -> Unit
                is DeviceTokenPoll.SlowDown -> interval += result.extraDelaySeconds
                is DeviceTokenPoll.Expired -> {
                    state = OwnerLoginUiState.Failed("DEVICE_CODE_EXPIRED")
                    return@LaunchedEffect
                }
                is DeviceTokenPoll.Denied -> {
                    state = OwnerLoginUiState.Failed("DEVICE_AUTHORIZATION_DENIED")
                    return@LaunchedEffect
                }
                is DeviceTokenPoll.Failed -> {
                    state = OwnerLoginUiState.Failed(result.message)
                    return@LaunchedEffect
                }
                is DeviceTokenPoll.Success -> {
                    val identity = try {
                        withContext(Dispatchers.IO) {
                            GitHubDeviceFlowClient.fetchIdentity(result.accessToken)
                        }
                    } catch (error: Throwable) {
                        state = OwnerLoginUiState.Failed(error.message ?: error.javaClass.simpleName)
                        return@LaunchedEffect
                    }

                    // The user token is intentionally not persisted in this foundation.
                    state = OwnerLoginUiState.Verified(
                        identity = identity,
                        expectedOwner = identity.id == GitHubAppPublicConfig.ownerGithubUserId,
                    )
                    return@LaunchedEffect
                }
            }
        }

        state = OwnerLoginUiState.Failed("DEVICE_CODE_EXPIRED")
    }

    Card {
        Column(
            Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(stringResource(R.string.owner_mode), fontWeight = FontWeight.Bold)

            when (val current = state) {
                OwnerLoginUiState.Idle -> {
                    Text(stringResource(R.string.owner_mode_public_viewer))
                    Button(onClick = ::beginLogin, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.sign_in_as_owner))
                    }
                }

                OwnerLoginUiState.Requesting -> {
                    Text(stringResource(R.string.owner_login_requesting))
                }

                is OwnerLoginUiState.Waiting -> {
                    Text(stringResource(R.string.owner_login_code_label))
                    Text(
                        current.authorization.userCode,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(stringResource(R.string.owner_login_waiting))
                    OutlinedButton(
                        onClick = { uriHandler.openUri(current.authorization.verificationUri) },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.open_github))
                    }
                }

                is OwnerLoginUiState.Verified -> {
                    if (current.expectedOwner) {
                        Text(stringResource(R.string.owner_identity_verified, current.identity.login))
                        Text(stringResource(R.string.owner_backend_pending))
                    } else {
                        Text(stringResource(R.string.non_owner_identity, current.identity.login))
                    }
                    OutlinedButton(onClick = { state = OwnerLoginUiState.Idle }, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.reset_owner_login))
                    }
                }

                is OwnerLoginUiState.Failed -> {
                    Text(stringResource(R.string.owner_login_failed))
                    Text(current.message, color = MaterialTheme.colorScheme.error)
                    OutlinedButton(onClick = ::beginLogin, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.retry))
                    }
                }
            }
        }
    }
}
