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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class LocalizedMainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { LocalizedSourceLabTheme { LocalizedSourceLabApp() } }
    }
}

private enum class LocalizedScreen { Farm, Sources, Tests, Report }

private data class LocalizedSource(
    val name: String,
    val language: String,
    val providers: List<String>,
    val repaired: Boolean = false,
)

private sealed interface LocalizedSyncState {
    data object Loading : LocalizedSyncState
    data class Ready(val snapshot: LiveFarmSnapshot) : LocalizedSyncState
    data class Failed(val message: String) : LocalizedSyncState
}

private object LocalizedSeed {
    const val run = "35002747386"
    const val seedCommit = "4dc733270e4022c0eff9fe91479d3cf5e78eadbe"
    const val approvalCommit = "7dfce1617d24ebf1a7e21ed8e41412d79791a731"
    const val artifact = "10410915845"
    const val digest = "sha256:7e784bca4e49b5633c043d63fdb9066807716bffb17cc4070c1423de7b3e1439"

    val sources = listOf(
        LocalizedSource("Bacami", "ID", listOf("UMA", "Keiyoushi")),
        LocalizedSource("Kiryuu", "ID", listOf("UMA", "Keiyoushi")),
        LocalizedSource("Komiku", "ID", listOf("UMA", "Keiyoushi")),
        LocalizedSource("Shinigami", "ID", listOf("UMA", "Gekkoushi"), true),
        LocalizedSource("DoujinDesu.tv", "ID", listOf("Gekkoushi")),
        LocalizedSource("TheManga", "ID", listOf("UMA")),
        LocalizedSource("Asura Scans", "EN", listOf("UMA", "Keiyoushi", "Gekkoushi")),
        LocalizedSource("Aqua Manga", "EN", listOf("UMA", "Keiyoushi")),
        LocalizedSource("BatCave", "EN", listOf("UMA", "Keiyoushi", "Gekkoushi"), true),
        LocalizedSource("LikeManga", "EN", listOf("UMA")),
        LocalizedSource("Weeb Central", "EN", listOf("UMA")),
        LocalizedSource("MangaPill", "EN", listOf("UMA")),
    )
}

@Composable
private fun LocalizedSourceLabTheme(content: @Composable () -> Unit) {
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
private fun LocalizedSourceLabApp() {
    var screen by remember { mutableStateOf(LocalizedScreen.Farm) }
    var selected by remember { mutableStateOf<LocalizedSource?>(null) }
    var refresh by remember { mutableIntStateOf(0) }
    var sync by remember { mutableStateOf<LocalizedSyncState>(LocalizedSyncState.Loading) }

    LaunchedEffect(refresh) {
        sync = LocalizedSyncState.Loading
        sync = try {
            LocalizedSyncState.Ready(withContext(Dispatchers.IO) { SourceLabRepository.loadSnapshot() })
        } catch (error: Throwable) {
            LocalizedSyncState.Failed(error.message ?: error.javaClass.simpleName)
        }
    }

    val live = (sync as? LocalizedSyncState.Ready)?.snapshot
    val sources = live?.sources?.map {
        LocalizedSource(
            name = it.displayName,
            language = it.language,
            providers = it.providers.map(String::prettyProviderNameLocalized),
            repaired = it.displayName == "Shinigami" || it.displayName == "BatCave",
        )
    } ?: LocalizedSeed.sources

    Scaffold(
        bottomBar = {
            if (selected == null) {
                NavigationBar {
                    LocalizedNavItem(LocalizedScreen.Farm, screen, "F", R.string.nav_farm) { screen = it }
                    LocalizedNavItem(LocalizedScreen.Sources, screen, "S", R.string.nav_sources) { screen = it }
                    LocalizedNavItem(LocalizedScreen.Tests, screen, "T", R.string.nav_tests) { screen = it }
                    LocalizedNavItem(LocalizedScreen.Report, screen, "R", R.string.nav_report) { screen = it }
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            selected?.let { source ->
                LocalizedSourceDetail(source) { selected = null }
            } ?: when (screen) {
                LocalizedScreen.Farm -> LocalizedFarmScreen(live, sources.size, sync) { refresh++ }
                LocalizedScreen.Sources -> LocalizedSourcesScreen(sources) { selected = it }
                LocalizedScreen.Tests -> LocalizedTestsScreen(sync)
                LocalizedScreen.Report -> LocalizedReportScreen(live)
            }
        }
    }
}

@Composable
private fun RowScope.LocalizedNavItem(
    target: LocalizedScreen,
    current: LocalizedScreen,
    glyph: String,
    labelRes: Int,
    onClick: (LocalizedScreen) -> Unit,
) {
    NavigationBarItem(
        selected = target == current,
        onClick = { onClick(target) },
        icon = { Text(glyph, fontWeight = FontWeight.Bold) },
        label = { Text(stringResource(labelRes)) },
    )
}

@Composable
private fun LocalizedFarmScreen(
    snapshot: LiveFarmSnapshot?,
    sourceCount: Int,
    sync: LocalizedSyncState,
    onRefresh: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Text(stringResource(R.string.app_name), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(stringResource(R.string.dashboard_subtitle), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item { LocalizedLiveCard(sync, onRefresh) }
        item {
            LocalizedStatusCard(
                stringResource(R.string.checkpoint_title),
                "WAITING_FOR_APPROVAL",
                stringResource(R.string.checkpoint_supporting),
            )
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                LocalizedStatCard("$sourceCount/12", stringResource(R.string.registry_sources), Modifier.weight(1f))
                LocalizedStatCard("21/21", stringResource(R.string.seed_memberships), Modifier.weight(1f))
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                LocalizedStatCard("0", stringResource(R.string.seed_failures), Modifier.weight(1f))
                LocalizedStatCard("2/2", stringResource(R.string.auto_repair), Modifier.weight(1f))
            }
        }
        item { Text(stringResource(R.string.provider_runtime_vs_seed), fontWeight = FontWeight.Bold) }
        if (snapshot != null) {
            items(snapshot.providers, key = { it.id }) { provider ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(provider.id.prettyProviderNameLocalized(), fontWeight = FontWeight.Bold)
                            val count = snapshot.sources.count { provider.id in it.providers }
                            Text(
                                stringResource(R.string.registered_memberships_state, count, provider.updateState),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text(provider.runtimeHealth, fontWeight = FontWeight.Bold)
                            Text(stringResource(R.string.active_baseline), style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }
        }
        item { LocalizedSafetyCard() }
    }
}

@Composable
private fun LocalizedLiveCard(sync: LocalizedSyncState, onRefresh: () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when (sync) {
                LocalizedSyncState.Loading -> {
                    Text(stringResource(R.string.repository_sync), fontWeight = FontWeight.Bold)
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                    Text(stringResource(R.string.reading_farm_state))
                }
                is LocalizedSyncState.Ready -> {
                    Text(stringResource(R.string.live_read_only), fontWeight = FontWeight.Bold, color = Color(0xFF75E8B0))
                    Text(stringResource(R.string.live_sources_summary, sync.snapshot.cohort, sync.snapshot.sources.size, sync.snapshot.targetSize))
                    Text(stringResource(R.string.branch_label, sync.snapshot.branch))
                    OutlinedButton(onClick = onRefresh) { Text(stringResource(R.string.refresh)) }
                }
                is LocalizedSyncState.Failed -> {
                    Text(stringResource(R.string.live_sync_unavailable), fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.error)
                    Text(stringResource(R.string.fallback_checkpoint_message))
                    Text(sync.message, style = MaterialTheme.typography.bodySmall)
                    OutlinedButton(onClick = onRefresh) { Text(stringResource(R.string.retry)) }
                }
            }
        }
    }
}

@Composable
private fun LocalizedSourcesScreen(sources: List<LocalizedSource>, onOpen: (LocalizedSource) -> Unit) {
    var query by remember { mutableStateOf("") }
    var language by remember { mutableStateOf("ALL") }
    val visible = sources.filter {
        (language == "ALL" || it.language == language) && it.name.contains(query.trim(), ignoreCase = true)
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Text(stringResource(R.string.sources_title), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(stringResource(R.string.sources_subtitle), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                label = { Text(stringResource(R.string.search_source)) },
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("ALL", "ID", "EN").forEach { code ->
                    FilterChip(
                        selected = language == code,
                        onClick = { language = code },
                        label = { Text(if (code == "ALL") stringResource(R.string.filter_all) else code) },
                    )
                }
            }
        }
        items(visible, key = { it.name }) { source ->
            Card(
                modifier = Modifier.fillMaxWidth().clickable { onOpen(source) },
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.primary) {
                        Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) {
                            Text(source.name.first().uppercaseChar().toString(), fontWeight = FontWeight.Bold)
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(source.name, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text("${source.language} · ${source.providers.joinToString(" / ")}")
                    }
                    Text(
                        if (source.repaired) stringResource(R.string.repaired) else stringResource(R.string.registered),
                        color = Color(0xFF75E8B0),
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
            }
        }
    }
}

@Composable
private fun LocalizedTestsScreen(sync: LocalizedSyncState) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(stringResource(R.string.farm_title), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(stringResource(R.string.farm_subtitle), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item {
            LocalizedStatusCard(
                stringResource(R.string.authoritative_run, LocalizedSeed.run),
                "PASS",
                stringResource(R.string.authoritative_run_supporting),
            )
        }
        item {
            LocalizedEvidenceRow(stringResource(R.string.canonical_executed), "12 / 12")
            LocalizedEvidenceRow(stringResource(R.string.provider_memberships), "21 / 21")
            LocalizedEvidenceRow(stringResource(R.string.missing_memberships), "0")
            LocalizedEvidenceRow(stringResource(R.string.failing_memberships), "0")
            LocalizedEvidenceRow(stringResource(R.string.regression_budget), "0")
            LocalizedEvidenceRow(stringResource(R.string.repair_retest), "2 / 2")
        }
        item {
            Card {
                Column(Modifier.padding(16.dp)) {
                    Text(stringResource(R.string.live_registry_link), fontWeight = FontWeight.Bold)
                    Text(
                        when (sync) {
                            LocalizedSyncState.Loading -> stringResource(R.string.loading_farm_state)
                            is LocalizedSyncState.Ready -> stringResource(R.string.connected_read_only, sync.snapshot.branch)
                            is LocalizedSyncState.Failed -> stringResource(R.string.offline_fallback)
                        }
                    )
                }
            }
        }
        item {
            Card {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.remote_test_control), fontWeight = FontWeight.Bold)
                    Text(stringResource(R.string.remote_test_control_supporting))
                    Button(onClick = {}, enabled = false, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.run_full_farm_pending))
                    }
                }
            }
        }
        item {
            Card {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.approval), fontWeight = FontWeight.Bold)
                    Text(stringResource(R.string.approval_locked_supporting))
                    Button(onClick = {}, enabled = false, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.approve_exact_candidate_locked))
                    }
                    Text("publishEligible=false")
                }
            }
        }
    }
}

@Composable
private fun LocalizedReportScreen(snapshot: LiveFarmSnapshot?) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(stringResource(R.string.report_title), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(stringResource(R.string.report_subtitle), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item { LocalizedReportLine(stringResource(R.string.run_label), LocalizedSeed.run) }
        item { LocalizedReportLine(stringResource(R.string.seed_commit), LocalizedSeed.seedCommit) }
        item { LocalizedReportLine(stringResource(R.string.approval_engine), LocalizedSeed.approvalCommit) }
        item { LocalizedReportLine(stringResource(R.string.artifact), LocalizedSeed.artifact) }
        item { LocalizedReportLine(stringResource(R.string.digest), LocalizedSeed.digest) }
        snapshot?.let {
            item { LocalizedReportLine(stringResource(R.string.live_registry_branch), it.branch) }
            item { LocalizedReportLine(stringResource(R.string.live_registry_cohort), it.cohort) }
        }
        item {
            Card {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.gate_semantics), fontWeight = FontWeight.Bold)
                    Text("CANDIDATE → WAITING_FOR_APPROVAL")
                    Text("ownerActionRequired=false")
                    Text("publishEligible=false")
                    HorizontalDivider()
                    Text(stringResource(R.string.gate_safety_message))
                }
            }
        }
    }
}

@Composable
private fun LocalizedSourceDetail(source: LocalizedSource, onBack: () -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            TextButton(onClick = onBack) { Text(stringResource(R.string.back)) }
            Text(source.name, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text("${source.language} · ${source.providers.joinToString(" / ")}")
        }
        item {
            LocalizedStatusCard(
                stringResource(R.string.seed_compatibility_evidence),
                "PASS",
                stringResource(R.string.seed_compatibility_supporting, source.providers.size, source.providers.size),
            )
        }
        if (source.repaired) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF123229))) {
                    Column(Modifier.padding(16.dp)) {
                        Text(stringResource(R.string.auto_repair_validated), fontWeight = FontWeight.Bold, color = Color(0xFF75E8B0))
                        Text(stringResource(R.string.auto_repair_validated_supporting))
                    }
                }
            }
        }
        item { Text(stringResource(R.string.compatibility_contract), fontWeight = FontWeight.Bold) }
        val capabilities = listOf(
            R.string.capability_load,
            R.string.capability_browse,
            R.string.capability_search,
            R.string.capability_details,
            R.string.capability_chapters,
            R.string.capability_pages_content,
            R.string.capability_authentication,
            R.string.capability_download,
            R.string.capability_reader,
        )
        items(capabilities) { res ->
            LocalizedEvidenceRow(
                stringResource(res),
                if (res == R.string.capability_authentication) stringResource(R.string.per_source_policy) else stringResource(R.string.covered),
            )
        }
        item { Text(stringResource(R.string.runtime_candidate_separation), style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable
private fun LocalizedSafetyCard() {
    Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF171C2C))) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(stringResource(R.string.safety_boundary), fontWeight = FontWeight.Bold)
            Text(stringResource(R.string.safety_read_only))
            Text(stringResource(R.string.safety_pass_not_promote))
            Text(stringResource(R.string.safety_lkg_exact_approval))
            Text(stringResource(R.string.safety_stale_fail_closed))
            Text(stringResource(R.string.safety_no_write_token))
            Text(stringResource(R.string.safety_no_release_publish))
        }
    }
}

@Composable
private fun LocalizedStatusCard(title: String, status: String, supporting: String) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            Surface(shape = RoundedCornerShape(999.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = 0.18f)) {
                Text(status, Modifier.padding(horizontal = 10.dp, vertical = 5.dp), color = MaterialTheme.colorScheme.primary)
            }
            Text(supporting)
        }
    }
}

@Composable
private fun LocalizedStatCard(value: String, label: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(Modifier.padding(16.dp)) {
            Text(value, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(label)
        }
    }
}

@Composable
private fun LocalizedEvidenceRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
        Text(label, Modifier.weight(1f))
        Text("$value  ✓", color = Color(0xFF75E8B0), fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun LocalizedReportLine(label: String, value: String) {
    Card {
        Column(Modifier.padding(14.dp)) {
            Text(label, style = MaterialTheme.typography.labelMedium)
            Text(value)
        }
    }
}

private fun String.prettyProviderNameLocalized(): String = when (lowercase()) {
    "keiyoushi" -> "Keiyoushi"
    "uma" -> "UMA"
    "gekkoushi" -> "Gekkoushi"
    else -> replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
}
