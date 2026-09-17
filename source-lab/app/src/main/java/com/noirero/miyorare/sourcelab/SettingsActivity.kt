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
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

class SettingsActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceLabPhase1Theme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    SettingsScreen(onClose = { finish() })
                }
            }
        }
    }
}

@Composable
private fun SettingsScreen(onClose: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val owner = SourceLabOwnerSessionStore.get()
    val ownerDecision = SourceLabAccessPolicy.evaluate(owner)
    var cachedInventory by remember { mutableStateOf<SourceInventorySnapshot?>(null) }

    suspend fun readCache() {
        cachedInventory = SourceInventoryCacheReader.load(context)
    }

    LaunchedEffect(Unit) { readCache() }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "header") {
            TextButton(onClick = onClose) { Text("← Dashboard") }
            Text("Settings", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(
                "Source Lab preferences and operational information. Sensitive diagnostics and recovery controls stay separated from the normal approval workflow.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        item(key = "account") {
            SettingsSection("Account / Owner") {
                SettingsValue(
                    label = "Mode",
                    value = if (ownerDecision.canControl) "Owner" else "Public / unverified",
                    tone = if (ownerDecision.canControl) SourceLabTone.GOOD else SourceLabTone.NEUTRAL,
                )
                Text(
                    if (ownerDecision.canControl) {
                        "Owner session is available. Identity, repository permission and backend capability are still revalidated before control actions."
                    } else {
                        "No active verified Owner control session is available in this process."
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        item(key = "appearance") {
            SettingsSection("Appearance") {
                SettingsValue("Theme", "Dark operational", SourceLabTone.ACCENT)
                Text(
                    "Source Lab currently uses the shared dark navy / indigo operational theme. A theme switch is not exposed because this build has no persisted appearance preference backend.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        item(key = "cache") {
            SettingsSection("Cache & Storage") {
                val cache = cachedInventory
                SettingsValue(
                    label = "Source inventory cache",
                    value = if (cache == null) "Not available" else "${cache.sources.size} sources",
                    tone = if (cache == null) SourceLabTone.NEUTRAL else SourceLabTone.GOOD,
                )
                if (cache != null) {
                    val ageMinutes = cache.cacheAgeMillis / 60_000L
                    Text(
                        "Last cached inventory age · ${ageMinutes}m",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Text(
                    "Inventory is read from disk first and refreshed in the background. Normal navigation does not require a blocking inventory fetch.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedButton(
                    onClick = { scope.launch { readCache() } },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Refresh cache metadata") }
            }
        }

        item(key = "network") {
            SettingsSection("Network") {
                SettingsValue("Inventory", "Cached-first + background refresh", SourceLabTone.GOOD)
                SettingsValue("Farm state", "Live on demand", SourceLabTone.ACCENT)
                Text(
                    "Search and filtering are local once inventory is available. Large logs and provider diffs are loaded only when explicitly opened.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        item(key = "diagnostics") {
            SettingsSection("Diagnostics & Recovery") {
                Text(
                    "Routine upstream changes are detected and tested automatically. Manual Farm execution and stage recovery are retained only for exceptions; normal Owner work should stop at Review / Approve & Auto Publish.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedButton(
                    onClick = {
                        context.startActivity(Intent(context, SourceLabDiagnosticsActivity::class.java))
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Open Diagnostics") }
                OutlinedButton(
                    onClick = {
                        context.startActivity(Intent(context, FarmRunActivity::class.java))
                    },
                    enabled = ownerDecision.canControl,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Manual Run Farm · Recovery") }
                OutlinedButton(
                    onClick = {
                        context.startActivity(Intent(context, OwnerControlActivity::class.java))
                    },
                    enabled = ownerDecision.canControl,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Advanced Promote / Sign / Publish Recovery") }
                Text(
                    "Recovery screens still use the same fail-closed Owner/backend capability checks. They are not part of the routine autonomous path.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        item(key = "about") {
            SettingsSection("About") {
                SettingsValue("Miyorare Source Lab", BuildConfig.VERSION_NAME, SourceLabTone.NEUTRAL)
                Text(
                    "Compatibility Farm control plane / reader. Stable release signing and repository mutations remain outside the APK and are handled by authorized GitHub Actions workflows.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun SettingsSection(title: String, content: @Composable () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(
            Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(title, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

@Composable
private fun SettingsValue(label: String, value: String, tone: SourceLabTone) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, modifier = Modifier.weight(1f))
        SourceLabStatusBadge(value, tone)
    }
}
