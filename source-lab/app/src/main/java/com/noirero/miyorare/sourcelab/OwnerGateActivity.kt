package com.noirero.miyorare.sourcelab

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
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
import kotlinx.coroutines.delay

class OwnerGateActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (SourceLabOwnerSessionStore.get() != null) {
            openDashboard(ownerAuthorized = true)
            return
        }

        setContent {
            SourceLabPhase1Theme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    OwnerGateScreen(
                        operationScope = lifecycleScope,
                        onViewer = {
                            SourceLabOwnerSessionStore.clear()
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
        delay(600L)
        onOpenOwnerDashboard()
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item(key = "header") {
            Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                SourceLabStatusBadge("COMPATIBILITY FARM", SourceLabTone.ACCENT)
                Text(
                    text = stringResource(R.string.owner_gate_heading),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = stringResource(R.string.owner_gate_subtitle),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        item(key = "viewer") {
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = stringResource(R.string.public_viewer_title),
                            fontWeight = FontWeight.Bold,
                        )
                        SourceLabStatusBadge("READ ONLY", SourceLabTone.NEUTRAL)
                    }
                    Text(
                        text = stringResource(R.string.public_viewer_supporting),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Button(
                        onClick = onViewer,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.continue_as_viewer))
                    }
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
                Card(colors = CardDefaults.cardColors(containerColor = SourceLabSurface)) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(14.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = stringResource(R.string.opening_source_lab_dashboard),
                            color = SourceLabGood,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.weight(1f),
                        )
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
