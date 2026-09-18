package com.noirero.miyorare.sourcelab

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.CoroutineScope

class OwnerGateActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Always render the branded gate first. Saved Owner credentials are
        // restored by OwnerAuthorizationCard while the Viewer path remains
        // immediately usable and fail-closed.
        setContent {
            SourceLabPhase1Theme {
                SourceLabAppSurface {
                    OwnerGateScreen(
                        operationScope = lifecycleScope,
                        onViewer = {
                            SourceLabOwnerSessionStore.enterViewerMode()
                            SourceLabControlClient.clearCachedOwnerContext()
                            openDashboard(ownerAuthorized = false)
                        },
                        onAuthorized = { session ->
                            SourceLabOwnerSessionStore.set(session)
                        },
                        onOpenOwnerDashboard = {
                            openDashboard(ownerAuthorized = true)
                        },
                    )
                }
            }
        }
    }

    private fun openDashboard(ownerAuthorized: Boolean) {
        val target = if (ownerAuthorized) AutonomousOwnerControlActivity::class.java else LocalizedMainActivity::class.java
        startActivity(
            Intent(this, target).apply {
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                putExtra("source_lab_backend_authorized", ownerAuthorized)
                val session = SourceLabOwnerSessionStore.get()
                putExtra(
                    "source_lab_backend_authorization_expires_at",
                    session?.backendAuthorizationExpiresAtEpochSeconds ?: 0L,
                )
            },
        )
        finish()
    }
}

@Composable
private fun OwnerGateScreen(
    operationScope: CoroutineScope,
    onViewer: () -> Unit,
    onAuthorized: (OwnerAccessSession) -> Unit,
    onOpenOwnerDashboard: () -> Unit,
) {
    var authorizedSession by remember { mutableStateOf<OwnerAccessSession?>(null) }

    LaunchedEffect(authorizedSession) {
        val session = authorizedSession ?: return@LaunchedEffect
        onAuthorized(session)
        onOpenOwnerDashboard()
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 22.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item(key = "brand") {
            Column(
                modifier = Modifier.fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                SourceLabLogo(Modifier.size(124.dp))
                Spacer(Modifier.height(2.dp))
                Text(
                    text = "Miyorare",
                    style = MaterialTheme.typography.headlineLarge,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = "Source Lab",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = SourceLabPrimarySoft,
                )
                Text(
                    text = stringResource(R.string.owner_gate_tagline),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    text = stringResource(R.string.owner_gate_supporting_short),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        item(key = "capabilities") {
            SourceLabCard(
                tone = SourceLabTone.ACCENT,
                contentPadding = PaddingValues(horizontal = 15.dp, vertical = 14.dp),
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(13.dp)) {
                    WelcomeCapabilityRow(
                        title = stringResource(R.string.owner_gate_capability_load),
                        supporting = stringResource(R.string.owner_gate_capability_load_supporting),
                        icon = SourceLabIconKind.SOURCES,
                    )
                    WelcomeCapabilityRow(
                        title = stringResource(R.string.owner_gate_capability_test),
                        supporting = stringResource(R.string.owner_gate_capability_test_supporting),
                        icon = SourceLabIconKind.TEST,
                    )
                    WelcomeCapabilityRow(
                        title = stringResource(R.string.owner_gate_capability_results),
                        supporting = stringResource(R.string.owner_gate_capability_results_supporting),
                        icon = SourceLabIconKind.REPORTS,
                    )
                    WelcomeCapabilityRow(
                        title = stringResource(R.string.owner_gate_capability_approval),
                        supporting = stringResource(R.string.owner_gate_capability_approval_supporting),
                        icon = SourceLabIconKind.CHECK,
                    )
                }
            }
        }

        item(key = "viewer") {
            SourceLabCard {
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(11.dp),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                text = stringResource(R.string.public_viewer_title),
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                            )
                            Text(
                                text = stringResource(R.string.public_viewer_supporting),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        SourceLabStatusBadge("READ ONLY", SourceLabTone.NEUTRAL)
                    }
                    SourceLabPrimaryButton(
                        text = stringResource(R.string.continue_as_viewer),
                        onClick = onViewer,
                        modifier = Modifier.fillMaxWidth(),
                        icon = SourceLabIconKind.ARROW_RIGHT,
                    )
                }
            }
        }

        item(key = "owner") {
            OwnerAuthorizationCard(
                operationScope = operationScope,
                onSessionChanged = { session ->
                    authorizedSession = session
                },
            )
        }

        if (authorizedSession != null) {
            item(key = "opening") {
                SourceLabCard(tone = SourceLabTone.GOOD) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Row(
                            Modifier.weight(1f),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(9.dp),
                        ) {
                            Box(
                                Modifier.size(30.dp),
                                contentAlignment = Alignment.Center,
                            ) {
                                SourceLabIcon(SourceLabIconKind.CHECK, Modifier.size(20.dp), SourceLabGood)
                            }
                            Text(
                                text = stringResource(R.string.opening_source_lab_dashboard),
                                color = SourceLabGood,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                        SourceLabStatusBadge("OWNER", SourceLabTone.GOOD)
                    }
                }
            }
        }

        item(key = "boundary") {
            Text(
                text = stringResource(R.string.owner_gate_capability_boundary),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun WelcomeCapabilityRow(
    title: String,
    supporting: String,
    icon: SourceLabIconKind,
) {
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(11.dp),
    ) {
        Box(
            Modifier.size(38.dp),
            contentAlignment = Alignment.Center,
        ) {
            SourceLabIcon(icon, Modifier.size(21.dp), SourceLabPrimarySoft)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
            Text(
                supporting,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        SourceLabIcon(SourceLabIconKind.CHECK, Modifier.size(16.dp), SourceLabGood)
    }
}
