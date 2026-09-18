package com.noirero.miyorare.sourcelab

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
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
        GitHubOwnerCredentialVault.save(context, identity.credential)
        verifiedIdentity = identity
        authorizeBackend(identity)
    }

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

    SourceLabCard(tone = SourceLabTone.ACCENT) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(11.dp),
        ) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(
                    Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(9.dp),
                ) {
                    Box(Modifier.size(36.dp), contentAlignment = Alignment.Center) {
                        SourceLabIcon(SourceLabIconKind.USER, Modifier.size(22.dp), SourceLabPrimarySoft)
                    }
                    Column {
                        Text(
                            text = stringResource(R.string.owner_access_title),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = "GitHub + backend capability",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                SourceLabStatusBadge(
                    when (state) {
                        is OwnerAuthorizationUiState.Authorized -> "OWNER"
                        is OwnerAuthorizationUiState.Failed -> "LOCKED"
                        OwnerAuthorizationUiState.RestoringOwner,
                        OwnerAuthorizationUiState.AuthorizingBackend,
                        is OwnerAuthorizationUiState.WaitingForGitHub -> "VERIFYING"
                        OwnerAuthorizationUiState.Idle -> "SECURE"
                    },
                    when (state) {
                        is OwnerAuthorizationUiState.Authorized -> SourceLabTone.GOOD
                        is OwnerAuthorizationUiState.Failed -> SourceLabTone.ERROR
                        OwnerAuthorizationUiState.RestoringOwner,
                        OwnerAuthorizationUiState.AuthorizingBackend,
                        is OwnerAuthorizationUiState.WaitingForGitHub -> SourceLabTone.ACCENT
                        OwnerAuthorizationUiState.Idle -> SourceLabTone.NEUTRAL
                    },
                )
            }

            Text(
                text = stringResource(R.string.owner_access_supporting),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
            )

            when (val current = state) {
                OwnerAuthorizationUiState.Idle -> {
                    SourceLabPrimaryButton(
                        text = stringResource(R.string.connect_github_owner),
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
                        icon = SourceLabIconKind.LOCK,
                    )
                    if (!embeddedClientIdAvailable) {
                        Text(
                            text = stringResource(R.string.github_client_id_build_missing),
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodySmall,
                        )
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
                    SourceLabCard(
                        tone = SourceLabTone.ACCENT,
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(13.dp),
                    ) {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                text = stringResource(R.string.github_device_code_copied),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text(
                                text = current.code.userCode,
                                style = MaterialTheme.typography.headlineSmall,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace,
                                color = SourceLabPrimarySoft,
                            )
                            Text(
                                stringResource(R.string.github_waiting_authorization),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    SourceLabPrimaryButton(
                        text = stringResource(R.string.copy_github_code),
                        onClick = { copyUserCodeForPaste(context, current.code.userCode) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    SourceLabSecondaryButton(
                        text = stringResource(R.string.open_github_again),
                        onClick = {
                            copyUserCodeForPaste(context, current.code.userCode)
                            openVerificationPage(context, current.code.verificationUri)
                        },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }

                OwnerAuthorizationUiState.AuthorizingBackend -> {
                    AuthorizationProgress(stringResource(R.string.authorizing_backend))
                }

                is OwnerAuthorizationUiState.Authorized -> {
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(9.dp),
                    ) {
                        SourceLabIcon(SourceLabIconKind.CHECK, Modifier.size(20.dp), SourceLabGood)
                        Column(Modifier.weight(1f)) {
                            Text(
                                text = stringResource(R.string.backend_authorized),
                                fontWeight = FontWeight.Bold,
                                color = SourceLabGood,
                            )
                            Text(
                                text = stringResource(R.string.backend_authorized_supporting),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                    SourceLabSecondaryButton(
                        text = stringResource(R.string.forget_owner_device),
                        onClick = {
                            GitHubOwnerCredentialVault.clear(context)
                            verifiedIdentity = null
                            onSessionChanged(null)
                            state = OwnerAuthorizationUiState.Idle
                        },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }

                is OwnerAuthorizationUiState.Failed -> {
                    SourceLabCard(
                        tone = SourceLabTone.ERROR,
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(13.dp),
                    ) {
                        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            Text(
                                text = stringResource(R.string.owner_authorization_failed),
                                fontWeight = FontWeight.Bold,
                                color = SourceLabError,
                            )
                            Text(
                                text = ownerAuthorizationErrorMessage(current.reason),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                style = MaterialTheme.typography.bodySmall,
                            )
                            Text(
                                text = current.reason,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontFamily = FontFamily.Monospace,
                            )
                        }
                    }

                    val identity = verifiedIdentity
                    if (identity != null && current.reason.startsWith("BACKEND_")) {
                        SourceLabPrimaryButton(
                            text = stringResource(R.string.retry_backend_authorization),
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
                        )
                        SourceLabSecondaryButton(
                            text = stringResource(R.string.restart_github_sign_in),
                            onClick = {
                                GitHubOwnerCredentialVault.clear(context)
                                verifiedIdentity = null
                                state = OwnerAuthorizationUiState.Idle
                            },
                            modifier = Modifier.fillMaxWidth(),
                        )
                    } else {
                        SourceLabPrimaryButton(
                            text = stringResource(R.string.retry),
                            onClick = {
                                verifiedIdentity = null
                                state = OwnerAuthorizationUiState.Idle
                            },
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }

            Spacer(Modifier.height(1.dp))
            Text(
                text = stringResource(R.string.owner_token_secure_storage),
                style = MaterialTheme.typography.labelSmall,
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
        CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = SourceLabPrimary)
        Text(label, style = MaterialTheme.typography.bodyMedium)
    }
}

private fun copyUserCodeForPaste(context: Context, userCode: String) {
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
