package com.noirero.miyorare.sourcelab

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceLabTheme {
                SourceLabApp()
            }
        }
    }
}

private enum class Screen(val label: String, val glyph: String) {
    Dashboard("Farm", "F"),
    Sources("Sources", "S"),
    Tests("Tests", "T"),
    Report("Report", "R")
}

private data class SourceItem(
    val name: String,
    val language: String,
    val providers: List<String>,
    val repairValidated: Boolean = false,
)

private data class ProviderStat(
    val name: String,
    val memberships: Int,
    val runtimeHealth: String,
)

private object Seed12 {
    const val authoritativeRun = "35002747386"
    const val seedCommit = "4dc733270e4022c0eff9fe91479d3cf5e78eadbe"
    const val approvalFoundationCommit = "7dfce1617d24ebf1a7e21ed8e41412d79791a731"
    const val artifactId = "10410915845"
    const val artifactDigest = "sha256:7e784bca4e49b5633c043d63fdb9066807716bffb17cc4070c1423de7b3e1439"

    val providers = listOf(
        ProviderStat("Keiyoushi", 6, "HEALTHY"),
        ProviderStat("UMA", 11, "DEGRADED"),
        ProviderStat("Gekkoushi", 4, "DEGRADED"),
    )

    val sources = listOf(
        SourceItem("Bacami", "ID", listOf("UMA", "Keiyoushi")),
        SourceItem("Kiryuu", "ID", listOf("UMA", "Keiyoushi")),
        SourceItem("Komiku", "ID", listOf("UMA", "Keiyoushi")),
        SourceItem("Shinigami", "ID", listOf("UMA", "Gekkoushi"), repairValidated = true),
        SourceItem("DoujinDesu.tv", "ID", listOf("Gekkoushi")),
        SourceItem("TheManga", "ID", listOf("UMA")),
        SourceItem("Asura Scans", "EN", listOf("UMA", "Keiyoushi", "Gekkoushi")),
        SourceItem("Aqua Manga", "EN", listOf("UMA", "Keiyoushi")),
        SourceItem("BatCave", "EN", listOf("UMA", "Keiyoushi", "Gekkoushi"), repairValidated = true),
        SourceItem("LikeManga", "EN", listOf("UMA")),
        SourceItem("Weeb Central", "EN", listOf("UMA")),
        SourceItem("MangaPill", "EN", listOf("UMA")),
    )
}

@Composable
private fun SourceLabTheme(content: @Composable () -> Unit) {
    val scheme = darkColorScheme(
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
    )
    MaterialTheme(colorScheme = scheme, content = content)
}

@Composable
private fun SourceLabApp() {
    var screen by remember { mutableStateOf(Screen.Dashboard) }
    var selectedSource by remember { mutableStateOf<SourceItem?>(null) }

    Scaffold(
        bottomBar = {
            if (selectedSource == null) {
                NavigationBar {
                    Screen.entries.forEach { item ->
                        NavigationBarItem(
                            selected = screen == item,
                            onClick = { screen = item },
                            icon = { Text(item.glyph, fontWeight = FontWeight.Bold) },
                            label = { Text(item.label) },
                        )
                    }
                }
            }
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            selectedSource?.let { source ->
                SourceDetailScreen(source = source, onBack = { selectedSource = null })
            } ?: when (screen) {
                Screen.Dashboard -> DashboardScreen(onOpenSources = { screen = Screen.Sources })
                Screen.Sources -> SourcesScreen(onOpen = { selectedSource = it })
                Screen.Tests -> TestsScreen()
                Screen.Report -> ReportScreen()
            }
        }
    }
}

@Composable
private fun DashboardScreen(onOpenSources: () -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Text("Miyorare Source Lab", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(4.dp))
            Text("Compatibility Farm control panel · read-only foundation", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        item {
            StatusCard(
                title = "Seed-12 authoritative checkpoint",
                status = "WAITING_FOR_APPROVAL",
                supporting = "Real parser evidence complete. Publishing remains intentionally blocked.",
            )
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatCard("12/12", "Canonical", Modifier.weight(1f))
                StatCard("21/21", "Memberships", Modifier.weight(1f))
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatCard("0", "Failures", Modifier.weight(1f))
                StatCard("2/2", "Auto-repair", Modifier.weight(1f))
            }
        }

        item {
            SectionTitle("Provider runtime vs seed evidence")
        }
        items(Seed12.providers) { provider ->
            ProviderCard(provider)
        }

        item {
            SafetyCard()
        }

        item {
            Button(onClick = onOpenSources, modifier = Modifier.fillMaxWidth()) {
                Text("Browse 12 verified sources")
            }
        }
    }
}

@Composable
private fun SourcesScreen(onOpen: (SourceItem) -> Unit) {
    var query by remember { mutableStateOf("") }
    var language by remember { mutableStateOf("ALL") }
    val visible = remember(query, language) {
        Seed12.sources.filter {
            (language == "ALL" || it.language == language) &&
                it.name.contains(query.trim(), ignoreCase = true)
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Text("Sources", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text("Seed-12 canonical registry", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                label = { Text("Search source") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("ALL", "ID", "EN").forEach { item ->
                    FilterChip(
                        selected = language == item,
                        onClick = { language = item },
                        label = { Text(item) },
                    )
                }
            }
        }

        items(visible, key = { it.name }) { source ->
            SourceCard(source = source, onClick = { onOpen(source) })
        }
    }
}

@Composable
private fun TestsScreen() {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text("Compatibility Farm", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text("Authoritative evidence, not fixture-only status", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        item {
            StatusCard(
                title = "Authoritative run ${Seed12.authoritativeRun}",
                status = "PASS",
                supporting = "Real parser execution: true · full canonical coverage: true · full membership coverage: true",
            )
        }

        item {
            EvidenceRow("Canonical executed", "12 / 12", true)
            EvidenceRow("Provider memberships", "21 / 21", true)
            EvidenceRow("Missing memberships", "0", true)
            EvidenceRow("Failing memberships", "0", true)
            EvidenceRow("Regression budget", "0", true)
            EvidenceRow("Repair retest", "2 / 2", true)
        }

        item {
            Card {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Remote test control", fontWeight = FontWeight.Bold)
                    Text(
                        "The Android shell is ready for CI controls, but workflow dispatch/auth is deliberately not wired in this first foundation commit.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Button(onClick = {}, enabled = false, modifier = Modifier.fillMaxWidth()) {
                        Text("Run Full Farm · wiring pending")
                    }
                }
            }
        }

        item {
            Card {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Approval", fontWeight = FontWeight.Bold)
                    Text("Exact-SHA approval UI is visible only as a safety placeholder until P0 upstream authorization wiring is complete.")
                    Button(onClick = {}, enabled = false, modifier = Modifier.fillMaxWidth()) {
                        Text("Approve exact candidate · locked")
                    }
                    Text("publishEligible=false", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun ReportScreen() {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text("Evidence Report", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text("Provenance for the verified seed checkpoint", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item { ReportLine("Run", Seed12.authoritativeRun) }
        item { ReportLine("Seed commit", Seed12.seedCommit) }
        item { ReportLine("Approval engine", Seed12.approvalFoundationCommit) }
        item { ReportLine("Artifact", Seed12.artifactId) }
        item { ReportLine("Digest", Seed12.artifactDigest) }
        item {
            Card {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Gate semantics", fontWeight = FontWeight.Bold)
                    Text("CANDIDATE → WAITING_FOR_APPROVAL")
                    Text("ownerActionRequired=false")
                    Text("publishEligible=false")
                    HorizontalDivider()
                    Text(
                        "PASS never means PROMOTED. LKG/upstreamBase must not move until exact approval authorization succeeds.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun SourceDetailScreen(source: SourceItem, onBack: () -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            TextButton(onClick = onBack) { Text("← Back") }
            Text(source.name, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                BadgeText(source.language)
                BadgeText(source.providers.joinToString(" · "))
            }
        }

        item {
            StatusCard(
                title = "Seed compatibility evidence",
                status = "PASS",
                supporting = "${source.providers.size}/${source.providers.size} provider memberships exercised with real-parser coverage.",
            )
        }

        if (source.repairValidated) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF123229))) {
                    Column(Modifier.padding(16.dp)) {
                        Text("AUTO-REPAIR VALIDATED", fontWeight = FontWeight.Bold, color = Color(0xFF75E8B0))
                        Text("Generic repair was applied and the real parser retest passed.")
                    }
                }
            }
        }

        item { SectionTitle("Compatibility contract") }
        items(listOf("Load", "Browse", "Search", "Details", "Chapters", "Pages / content", "Authentication", "Download", "Reader")) { capability ->
            EvidenceRow(capability, if (capability == "Authentication") "Per source policy" else "Covered", true)
        }

        item {
            Text(
                "This screen intentionally does not label the active runtime HEALTHY from fixture/shape checks. Runtime health and candidate evidence remain separate concepts.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun SourceCard(source: SourceItem, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Row(
            Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.primary) {
                Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) {
                    Text(source.name.first().uppercaseChar().toString(), fontWeight = FontWeight.Bold)
                }
            }
            Column(Modifier.weight(1f)) {
                Text(source.name, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("${source.language} · ${source.providers.joinToString(" / ")}", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Text(if (source.repairValidated) "REPAIRED ✓" else "PASS ✓", color = Color(0xFF75E8B0), style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
private fun ProviderCard(stat: ProviderStat) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(stat.name, fontWeight = FontWeight.Bold)
                Text("Seed evidence ${stat.memberships}/${stat.memberships} PASS", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(stat.runtimeHealth, fontWeight = FontWeight.Bold)
                Text("active baseline", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun StatusCard(title: String, status: String, supporting: String) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            Surface(shape = RoundedCornerShape(999.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = 0.18f)) {
                Text(status, modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp), color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
            }
            Text(supporting, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun SafetyCard() {
    Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF171C2C))) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text("Safety boundary", fontWeight = FontWeight.Bold)
            Text("• PASS does not promote")
            Text("• LKG does not move before exact approval")
            Text("• stale approval must fail closed")
            Text("• no sign / release / publish from this foundation")
        }
    }
}

@Composable
private fun StatCard(value: String, label: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(Modifier.padding(16.dp)) {
            Text(value, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun EvidenceRow(label: String, value: String, pass: Boolean) {
    Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f))
        Text(if (pass) "$value  ✓" else value, color = if (pass) Color(0xFF75E8B0) else MaterialTheme.colorScheme.error, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun ReportLine(label: String, value: String) {
    Card {
        Column(Modifier.padding(14.dp)) {
            Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
}

@Composable
private fun BadgeText(text: String) {
    Surface(shape = RoundedCornerShape(999.dp), color = MaterialTheme.colorScheme.surfaceVariant) {
        Text(text, modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp), style = MaterialTheme.typography.labelMedium)
    }
}
