package com.noirero.miyorare.sourcelab

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

private sealed interface OwnerAuthorizationUiState {
    data object Idle : OwnerAuthorizationUiState
    data class WaitingForGitHub(val code: GitHubDeviceCode) : OwnerAuthorizationUiState
    data object AuthorizingBackend : OwnerAuthorizationUiState
    data class Authorized(val expiresAtEpochSeconds: Long) : OwnerAuthorizationUiState
    data class Failed(val reason: String) : OwnerAuthorizationUiState
}

@Composable
internal fun OwnerAuthorizationCard(
    onSessionChanged: (OwnerAccessSession?) -> Unit,
) {
    val context = LocalContext.current
    val preferences = remember {
        context.getSharedPreferences("source_lab_public_config", Context.MODE_PRIVATE)
    }
    var clientId by remember {
        mutableStateOf(preferences.getString("github_app_client_id", "").orEmpty())
    }
    var state by remember { mutableStateOf<OwnerAuthorizationUiState>(OwnerAuthorizationUiState.Idle) }
    val scope = rememberCoroutineScope()
    val busy = state is OwnerAuthorizationUiState.AuthorizingBackend ||
        state is OwnerAuthorizationUiState.WaitingForGitHub

    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = stringResource(R.string.owner_access_title),
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = stringResource(R.string.owner_access_supporting),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            OutlinedTextField(
                value = clientId,
                onValueChange = { value ->
                    clientId = value.trim()
                    preferences.edit().putString("github_app_client_id", clientId).apply()
                    if (state is OwnerAuthorizationUiState.Failed) {
                        state = OwnerAuthorizationUiState.Idle
                    }
                },
                enabled = !busy,
                singleLine = true,
                label = { Text(stringResource(R.string.github_client_id)) },
                supportingText = { Text(stringResource(R.string.github_client_id_supporting)) },
                modifier = Modifier.fillMaxWidth(),
            )

            when (val current = state) {
                OwnerAuthorizationUiState.Idle -> {
                    Button(
                        onClick = {
                            scope.launch {
                                onSessionChanged(null)
                                try {
                                    val resolvedClientId = GitHubOwnerAuthentication.resolveClientId(clientId)
                                    if (resolvedClientId != clientId) {
                                        clientId = resolvedClientId
                                        preferences.edit()
                                            .putString("github_app_client_id", resolvedClientId)
                                            .apply()
                                    }
                                    val code = GitHubOwnerAuthentication.requestDeviceCode(resolvedClientId)
                                    copyUserCode(context, code.userCode)
                                    state = OwnerAuthorizationUiState.WaitingForGitHub(code)
                                    openVerificationPage(context, code.verificationUri)
                                    val identity = GitHubOwnerAuthentication.completeOwnerLogin(resolvedClientId, code)
                                    state = OwnerAuthorizationUiState.AuthorizingBackend
                                    val proof = SourceLabBackendAuthorization.authorize(identity.accessToken)
                                    val authorizedSession = proof.applyTo(identity.session)
                                    val decision = SourceLabAccessPolicy.evaluate(authorizedSession)
                                    if (!decision.canControl) {
                                        onSessionChanged(null)
                                        state = OwnerAuthorizationUiState.Failed(
                                            if (!proof.authorized) proof.reason else decision.reason,
                                        )
                                    } else {
                                        onSessionChanged(authorizedSession)
                                        state = OwnerAuthorizationUiState.Authorized(
                                            proof.expiresAtEpochSeconds ?: 0L,
                                        )
                                    }
                                } catch (error: GitHubOwnerAuthenticationException) {
                                    onSessionChanged(null)
                                    state = OwnerAuthorizationUiState.Failed(error.reason)
                                } catch (_: Throwable) {
                                    onSessionChanged(null)
                                    state = OwnerAuthorizationUiState.Failed("OWNER_LOGIN_UNEXPECTED_ERROR")
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.connect_github_owner))
                    }
                }

                is OwnerAuthorizationUiState.WaitingForGitHub -> {
                    Text(stringResource(R.string.github_device_code_copied))
                    Text(
                        text = current.code.userCode,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace,
                    )
                    Text(
                        stringResource(R.string.github_waiting_authorization),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        CircularProgressIndicator()
                        OutlinedButton(
                            onClick = {
                                copyUserCode(context, current.code.userCode)
                                openVerificationPage(context, current.code.verificationUri)
                            },
                            modifier = Modifier.weight(1f),
                        ) {
                            Text(stringResource(R.string.open_github_again))
                        }
                    }
                }

                OwnerAuthorizationUiState.AuthorizingBackend -> {
                    AuthorizationProgress(stringResource(R.string.authorizing_backend))
                }

                is OwnerAuthorizationUiState.Authorized -> {
                    Text(
                        text = stringResource(R.string.backend_authorized),
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.tertiary,
                    )
                    Text(
                        text = stringResource(R.string.backend_authorized_supporting),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedButton(
                        onClick = {
                            onSessionChanged(null)
                            state = OwnerAuthorizationUiState.Idle
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.reauthorize_owner))
                    }
                }

                is OwnerAuthorizationUiState.Failed -> {
                    Text(
                        text = stringResource(R.string.owner_authorization_failed),
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.error,
                    )
                    Text(
                        text = current.reason,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontFamily = FontFamily.Monospace,
                    )
                    Button(
                        onClick = { state = OwnerAuthorizationUiState.Idle },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.retry))
                    }
                }
            }

            Spacer(Modifier.height(2.dp))
            Text(
                text = stringResource(R.string.owner_token_memory_only),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun AuthorizationProgress(label: String) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        CircularProgressIndicator()
        Text(label)
    }
}

private fun copyUserCode(context: Context, userCode: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    clipboard.setPrimaryClip(ClipData.newPlainText("GitHub device code", userCode))
}

private fun openVerificationPage(context: Context, verificationUri: String) {
    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(verificationUri)).apply {
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }
    context.startActivity(intent)
}
