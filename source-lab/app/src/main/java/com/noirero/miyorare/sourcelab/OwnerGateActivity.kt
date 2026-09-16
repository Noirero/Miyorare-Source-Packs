package com.noirero.miyorare.sourcelab

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
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
import kotlinx.coroutines.delay

internal object SourceLabOwnerSessionStore {
    @Volatile
    private var session: OwnerAccessSession? = null

    fun set(value: OwnerAccessSession?) {
        session = value
    }

    fun currentValid(): OwnerAccessSession? {
        val value = session ?: return null
        if (!SourceLabAccessPolicy.evaluate(value).canControl) {
            session = null
            return null
        }
        return value
    }
}

class OwnerGateActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (SourceLabOwnerSessionStore.currentValid() != null) {
            openDashboard()
            return
        }

        setContent {
            OwnerGateTheme {
                OwnerGateScreen(
                    onAuthorized = { session ->
                        SourceLabOwnerSessionStore.set(session)
                    },
                    onOpenDashboard = ::openDashboard,
                )
            }
        }
    }

    private fun openDashboard() {
        val valid = SourceLabOwnerSessionStore.currentValid()
        if (valid == null) return
        startActivity(
            Intent(this, LocalizedMainActivity::class.java).apply {
                putExtra("source_lab_backend_authorized", true)
                putExtra(
                    "source_lab_backend_authorization_expires_at",
                    valid.backendAuthorizationExpiresAtEpochSeconds ?: 0L,
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
    onAuthorized: (OwnerAccessSession) -> Unit,
    onOpenDashboard: () -> Unit,
) {
    var authorizedSession by remember { mutableStateOf<OwnerAccessSession?>(null) }

    LaunchedEffect(authorizedSession) {
        val session = authorizedSession ?: return@LaunchedEffect
        onAuthorized(session)
        delay(900L)
        onOpenDashboard()
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
            OwnerAuthorizationCard { session ->
                authorizedSession = session
            }
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
