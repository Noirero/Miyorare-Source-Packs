package com.noirero.miyorare.sourcelab

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
            OwnerGateTheme {
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

    private fun openDashboard(ownerAuthorized: Boolean) {
        val target = if (ownerAuthorized) OwnerControlActivity::class.java else LocalizedMainActivity::class.java
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
private fun OwnerGateTheme(content: @Composable () -> Unit) {
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
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
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

        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text(
                        text = stringResource(R.string.public_viewer_title),
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = stringResource(R.string.public_viewer_supporting),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
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

        item {
            OwnerAuthorizationCard(
                operationScope = operationScope,
                onSessionChanged = { session ->
                    authorizedSession = session
                },
            )
        }

        if (authorizedSession != null) {
            item {
                Text(
                    text = stringResource(R.string.opening_source_lab_dashboard),
                    color = MaterialTheme.colorScheme.tertiary,
                    fontWeight = FontWeight.Bold,
                )
            }
        }

        item {
            Text(
                text = stringResource(R.string.owner_gate_capability_boundary),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
