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
                SourceLabAppSurface {
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

    Box(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 16.dp, top = 16.dp, end = 16.dp, bottom = 96.dp),
            verticalArrangement = Arrangement.spacedBy(11.dp),
        ) {
            item(key = "header") {
                SourceLabTopBar(
                    title = "Settings",
                    subtitle = "Account, cache, network, and advanced controls.",
                )
            }

            item(key = "account") {
                SettingsSection("Account") {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                if (ownerDecision.canControl) "Owner mode" else "Viewer mode",
                                fontWeight = FontWeight.SemiBold,
                            )
                            Text(
                                if (ownerDecision.canControl) {
                                    "Verified session is available for read context; mutations still revalidate capabilities."
                                } else {
                                    "Public read-only access. Privileged controls remain unavailable."
                                },
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        SourceLabStatusBadge(
                            if (ownerDecision.canControl) "OWNER" else "VIEWER",
                            if (ownerDecision.canControl) SourceLabTone.GOOD else SourceLabTone.NEUTRAL,
                        )
                    }
                }
            }

            item(key = "appearance") {
                SettingsSection("Appearance") {
                    SettingsValue("Theme", "Dark premium", SourceLabTone.ACCENT)
                    Text(
                        "Miyorare Source Lab uses the shared dark navy interface with purple-blue operational accents.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            item(key = "cache") {
                SettingsSection("Data & Cache") {
                    val cache = cachedInventory
                    SettingsValue(
                        label = "Source inventory",
                        value = if (cache == null) "No cache" else "${cache.sources.size} sources",
                        tone = if (cache == null) SourceLabTone.NEUTRAL else SourceLabTone.GOOD,
                    )
                    if (cache != null) {
                        Text(
                            "Cache age · ${cache.cacheAgeMillis / 60_000L}m",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Text(
                        "Inventory remains cache-first and refreshes in the background. Search and filtering stay local once data is available.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    SourceLabSecondaryButton(
                        text = "Refresh cache metadata",
                        onClick = { scope.launch { readCache() } },
                        modifier = Modifier.fillMaxWidth(),
                        icon = SourceLabIconKind.REFRESH,
                    )
                }
            }

            item(key = "network") {
                SettingsSection("Network") {
                    SettingsValue("Inventory", "Cached-first", SourceLabTone.GOOD)
                    SettingsValue("Farm state", "Live on demand", SourceLabTone.ACCENT)
                    SettingsValue("Logs", "Load on demand", SourceLabTone.NEUTRAL)
                }
            }

            item(key = "advanced") {
                SettingsSection("Advanced") {
                    SourceLabStatusBadge("ADVANCED · RECOVERY", SourceLabTone.WARNING)
                    Text(
                        "Diagnostics and recovery are separated from the routine approval path. Every recovery action keeps the same fail-closed Owner/backend checks.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    SourceLabSecondaryButton(
                        text = "Diagnostics",
                        onClick = { context.startActivity(Intent(context, SourceLabDiagnosticsActivity::class.java)) },
                        modifier = Modifier.fillMaxWidth(),
                        icon = SourceLabIconKind.DOCUMENT,
                    )
                    SourceLabSecondaryButton(
                        text = "Manual Farm · Recovery",
                        onClick = { context.startActivity(Intent(context, FarmRunActivity::class.java)) },
                        enabled = ownerDecision.canControl,
                        modifier = Modifier.fillMaxWidth(),
                        icon = SourceLabIconKind.TEST,
                    )
                    SourceLabSecondaryButton(
                        text = "Promote / Sign / Publish Recovery",
                        onClick = { context.startActivity(Intent(context, OwnerControlActivity::class.java)) },
                        enabled = ownerDecision.canControl,
                        modifier = Modifier.fillMaxWidth(),
                        icon = SourceLabIconKind.WARNING,
                    )
                }
            }

            item(key = "about") {
                SettingsSection("About") {
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        SourceLabLogo(Modifier.size(52.dp), glow = false)
                        Column(Modifier.weight(1f)) {
                            Text("Miyorare Source Lab", fontWeight = FontWeight.Bold)
                            Text(
                                "Version ${BuildConfig.VERSION_NAME}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text(
                                "Test · Verify · Adapt · Approve",
                                style = MaterialTheme.typography.labelSmall,
                                color = SourceLabPrimarySoft,
                            )
                        }
                    }
                }
            }
        }

        SourceLabBottomBar(
            selected = SourceLabDestination.SETTINGS,
            onSelect = { destination -> openSourceLabDestination(context, destination) },
            modifier = Modifier.align(Alignment.BottomCenter).padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }


}

@Composable
private fun SettingsSection(title: String, content: @Composable () -> Unit) {
    SourceLabCard {
        Column(
            Modifier.fillMaxWidth(),
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
