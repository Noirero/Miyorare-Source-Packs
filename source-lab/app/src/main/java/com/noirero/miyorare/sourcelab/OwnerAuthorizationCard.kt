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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

private sealed interface OwnerAuthorizationUiState {
    data object Idle : OwnerAuthorizationUiState
    data object RestoringOwner : OwnerAuthorizationUiState
    data class WaitingForGitHub(val code: GitHubDeviceCode) : OwnerAuthorizationUiState
    data object AuthorizingBackend : OwnerAuthorizationUiState
    data class Authorized(val expiresAtEpochSeconds: Long) : OwnerAuthorizationUiState
    data class Failed(val reason: String) : OwnerAuthorizationUiState
}

@Composable
internal fun OwnerAuthorizationCard(
    operationScope: CoroutineScope,
    onSessionChanged: (OwnerAccessSession?) -> Unit,
) {
    val context = LocalContext.current
    var state by remember { mutableStateOf<OwnerAuthorizationUiState>(OwnerAuthorizationUiState.Idle) }
    var verifiedIdentity by remember { mutableStateOf<GitHubOwnerIdentity?>(null) }
    val busy = state is OwnerAuthorizationUiState.RestoringOwner ||
        state is OwnerAuthorizationUiState.AuthorizingBackend ||
        state is OwnerAuthorizationUiState.WaitingForGitHub
    val embeddedClientIdAvailable = remember {
        GitHubOwnerAuthentication.isValidClientId(BuildConfig.SOURCE_LAB_GITHUB_CLIENT_ID)
    }

    suspend fun authorizeBackend(identity: GitHubOwnerIdentity) {
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
            verifiedIdentity = null
            onSessionChanged(authorizedSession)
            state = OwnerAuthorizationUiState.Authorized(
                proof.expiresAtEpochSeconds ?: 0L,
            )
        }
    }

    suspend fun restoreSavedOwner(credential: GitHubOwnerCredential) {
        state = OwnerAuthorizationUiState.RestoringOwner
        val clientId = GitHubOwnerAuthentication.resolveClientId()
        val identity = GitHubOwnerAuthentication.restoreOwnerLogin(clientId, credential)
        // A refresh rotates the refresh token, so always persist the newest pair
        // before requesting a fresh short-lived backend proof.
        GitHubOwnerCredentialVault.save(context, identity.credential)
        verifiedIdentity = identity
        authorizeBackend(identity)
    }

    // Clean the obsolete manual Client ID recovery value and silently restore a
    // previously verified owner credential. The GitHub identity/install/repo
    // checks still run before a fresh backend authorization proof is accepted.
    LaunchedEffect(Unit) {
        context.getSharedPreferences("source_lab_public_config", Context.MODE_PRIVATE)
            .edit()
            .remove("github_app_client_id")
            .apply()

        if (!embeddedClientIdAvailable) return@LaunchedEffect
        val storedCredential = GitHubOwnerCredentialVault.load(context) ?: return@LaunchedEffect
        try {
            restoreSavedOwner(storedCredential)
        } catch (error: CancellationException) {
            throw error
        } catch (error: GitHubOwnerAuthenticationException) {
            if (shouldForgetStoredCredential(error.reason)) {
                GitHubOwnerCredentialVault.clear(context)
            }
            verifiedIdentity = null
            onSessionChanged(null)
            state = OwnerAuthorizationUiState.Failed(error.reason)
        } catch (_: Throwable) {
            verifiedIdentity = null
            onSessionChanged(null)
            state = OwnerAuthorizationUiState.Failed("OWNER_RESTORE_UNEXPECTED_ERROR")
        }
    }

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

            Text(
                text = stringResource(
                    if (embeddedClientIdAvailable) {
                        R.string.github_client_id_embedded_ready
                    } else {
                        R.string.github_client_id_build_missing
                    },
                ),
                color = if (embeddedClientIdAvailable) {
                    MaterialTheme.colorScheme.onSurfaceVariant
                } else {
                    MaterialTheme.colorScheme.error
                },
                style = MaterialTheme.typography.bodySmall,
            )

            when (val current = state) {
                OwnerAuthorizationUiState.Idle -> {
                    Button(
                        onClick = {
                            operationScope.launch {
                                onSessionChanged(null)
                                verifiedIdentity = null
                                try {
                                    val resolvedClientId = GitHubOwnerAuthentication.resolveClientId()
                                    val code = GitHubOwnerAuthentication.requestDeviceCode(resolvedClientId)
                                    copyUserCodeForPaste(context, code.userCode)
                                    state = OwnerAuthorizationUiState.WaitingForGitHub(code)
                                    openVerificationPage(context, code.verificationUri)
                                    val identity = GitHubOwnerAuthentication.completeOwnerLogin(resolvedClientId, code)
                                    // Save immediately after GitHub identity validation. If backend
                                    // authorization has a transient failure, the user does not have
                                    // to repeat Device Flow.
                                    GitHubOwnerCredentialVault.save(context, identity.credential)
                                    verifiedIdentity = identity
                                    authorizeBackend(identity)
                                } catch (error: CancellationException) {
                                    throw error
                                } catch (error: GitHubOwnerAuthenticationException) {
                                    if (shouldForgetStoredCredential(error.reason)) {
                                        GitHubOwnerCredentialVault.clear(context)
                                    }
                                    verifiedIdentity = null
                                    onSessionChanged(null)
                                    state = OwnerAuthorizationUiState.Failed(error.reason)
                                } catch (_: Throwable) {
                                    onSessionChanged(null)
                                    state = OwnerAuthorizationUiState.Failed("OWNER_LOGIN_UNEXPECTED_ERROR")
                                }
                            }
                        },
                        enabled = embeddedClientIdAvailable && !busy,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.connect_github_owner))
                    }
                }

                OwnerAuthorizationUiState.RestoringOwner -> {
                    AuthorizationProgress(stringResource(R.string.restoring_saved_owner))
                    Text(
                        text = stringResource(R.string.restoring_saved_owner_supporting),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
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
                        stringResource(R.string.github_paste_friendly_code),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        CircularProgressIndicator()
                        Text(
                            stringResource(R.string.github_waiting_authorization),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.weight(1f),
                        )
                    }
                    Button(
                        onClick = { copyUserCodeForPaste(context, current.code.userCode) },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.copy_github_code))
                    }
                    OutlinedButton(
                        onClick = {
                            copyUserCodeForPaste(context, current.code.userCode)
                            openVerificationPage(context, current.code.verificationUri)
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.open_github_again))
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
                            GitHubOwnerCredentialVault.clear(context)
                            verifiedIdentity = null
                            onSessionChanged(null)
                            state = OwnerAuthorizationUiState.Idle
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.forget_owner_device))
                    }
                }

                is OwnerAuthorizationUiState.Failed -> {
                    Text(
                        text = stringResource(R.string.owner_authorization_failed),
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.error,
                    )
                    Text(
                        text = ownerAuthorizationErrorMessage(current.reason),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        text = current.reason,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontFamily = FontFamily.Monospace,
                    )

                    val identity = verifiedIdentity
                    if (identity != null && current.reason.startsWith("BACKEND_")) {
                        Button(
                            onClick = {
                                operationScope.launch {
                                    try {
                                        authorizeBackend(identity)
                                    } catch (error: CancellationException) {
                                        throw error
                                    } catch (_: Throwable) {
                                        onSessionChanged(null)
                                        state = OwnerAuthorizationUiState.Failed(
                                            "BACKEND_AUTHORIZATION_UNEXPECTED_ERROR",
                                        )
                                    }
                                }
                            },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(stringResource(R.string.retry_backend_authorization))
                        }
                        OutlinedButton(
                            onClick = {
                                GitHubOwnerCredentialVault.clear(context)
                                verifiedIdentity = null
                                state = OwnerAuthorizationUiState.Idle
                            },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(stringResource(R.string.restart_github_sign_in))
                        }
                    } else {
                        Button(
                            onClick = {
                                verifiedIdentity = null
                                state = OwnerAuthorizationUiState.Idle
                            },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(stringResource(R.string.retry))
                        }
                    }
                }
            }

            Spacer(Modifier.height(2.dp))
            Text(
                text = stringResource(R.string.owner_token_secure_storage),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun shouldForgetStoredCredential(reason: String): Boolean = when (reason) {
    "GITHUB_SAVED_SESSION_EXPIRED",
    "GITHUB_IDENTITY_UNAUTHORIZED",
    "OWNER_ID_MISMATCH",
    "REPOSITORY_ID_MISMATCH",
    "INSUFFICIENT_REPOSITORY_PERMISSION",
    "INSTALLATION_MISMATCH",
    "GITHUB_APP_MISMATCH",
    "INSTALLATION_ACCOUNT_MISMATCH",
    "REPOSITORY_NOT_IN_INSTALLATION" -> true
    else -> false
}

@Composable
private fun ownerAuthorizationErrorMessage(reason: String): String = when {
    reason == "GITHUB_CLIENT_ID_NOT_CONFIGURED" -> stringResource(R.string.error_client_id_not_configured)
    reason == "GITHUB_CLIENT_ID_IS_INSTALLATION_ID" -> stringResource(R.string.error_client_id_is_installation_id)
    reason == "GITHUB_CLIENT_ID_IS_APP_ID" -> stringResource(R.string.error_client_id_is_app_id)
    reason == "GITHUB_CLIENT_ID_MUST_NOT_BE_NUMERIC" ||
        reason == "GITHUB_CLIENT_ID_FORMAT_INVALID" ||
        reason == "GITHUB_CLIENT_ID_INVALID" -> stringResource(R.string.error_client_id_invalid)
    reason == "GITHUB_SAVED_SESSION_EXPIRED" ||
        reason == "GITHUB_IDENTITY_UNAUTHORIZED" -> stringResource(R.string.error_saved_owner_expired)
    reason == "GITHUB_DEVICE_FLOW_ENDPOINT_NOT_FOUND" -> stringResource(R.string.error_device_flow_endpoint)
    reason.startsWith("BACKEND_") -> stringResource(R.string.error_backend_authorization)
    else -> stringResource(R.string.error_owner_generic)
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

private fun copyUserCodeForPaste(context: Context, userCode: String) {
    // GitHub displays the code as XXXX-XXXX, while its mobile entry UI uses
    // eight character slots. Copying only the eight characters is friendlier
    // to paste/autofill behavior on mobile keyboards and browsers.
    val pasteFriendlyCode = userCode.filter(Char::isLetterOrDigit).uppercase()
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    clipboard.setPrimaryClip(ClipData.newPlainText("GitHub device code", pasteFriendlyCode))
}

private fun openVerificationPage(context: Context, verificationUri: String) {
    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(verificationUri)).apply {
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }
    context.startActivity(intent)
}
