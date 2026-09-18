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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class LocalizedMainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { SourceLabPhase1Theme { SourceLabAppSurface { LocalizedSourceLabApp() } } }
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
    val context = LocalContext.current
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
        containerColor = Color.Transparent,
        bottomBar = {
            if (selected == null) {
                SourceLabBottomBar(
                    selected = SourceLabDestination.FARM,
                    onSelect = { destination ->
                        if (destination == SourceLabDestination.FARM) {
                            screen = LocalizedScreen.Farm
                        } else {
                            openSourceLabDestination(context, destination)
                        }
                    },
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                )
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
        icon = {
            SourceLabIcon(
                when (target) {
                    LocalizedScreen.Farm, LocalizedScreen.Tests -> SourceLabIconKind.FARM
                    LocalizedScreen.Sources -> SourceLabIconKind.SOURCES
                    LocalizedScreen.Report -> SourceLabIconKind.REPORTS
                },
                Modifier.size(20.dp),
                if (target == current) SourceLabPrimarySoft else SourceLabMuted,
            )
        },
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
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(11.dp),
    ) {
        item(key = "viewer-header") {
            SourceLabTopBar(
                title = stringResource(R.string.app_name),
                subtitle = "Compatibility Farm · public read-only",
                trailing = {
                    SourceLabStatusBadge("VIEWER", SourceLabTone.NEUTRAL)
                },
            )
        }

        item(key = "viewer-live") {
            LocalizedLiveCard(sync, onRefresh)
        }

        item(key = "viewer-checkpoint") {
            SourceLabCard(tone = SourceLabTone.WARNING) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                stringResource(R.string.checkpoint_title),
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                            )
                            Text(
                                stringResource(R.string.checkpoint_supporting),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        SourceLabStatusBadge("WAITING FOR APPROVAL", SourceLabTone.WARNING)
                    }
                    Text(
                        "Embedded checkpoint evidence is shown separately from live runtime state.",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        item(key = "viewer-metrics") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SourceLabMetricCard(
                        label = stringResource(R.string.registry_sources),
                        value = sourceCount.toString(),
                        modifier = Modifier.weight(1f),
                        tone = SourceLabTone.ACCENT,
                    )
                    SourceLabMetricCard(
                        label = stringResource(R.string.seed_memberships),
                        value = "21/21",
                        modifier = Modifier.weight(1f),
                        tone = SourceLabTone.GOOD,
                        supporting = "verified checkpoint",
                    )
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SourceLabMetricCard(
                        label = stringResource(R.string.seed_failures),
                        value = "0",
                        modifier = Modifier.weight(1f),
                        tone = SourceLabTone.GOOD,
                        supporting = "checkpoint",
                    )
                    SourceLabMetricCard(
                        label = stringResource(R.string.auto_repair),
                        value = "2/2",
                        modifier = Modifier.weight(1f),
                        tone = SourceLabTone.ACCENT,
                        supporting = "verified retest",
                    )
                }
            }
        }

        if (snapshot != null) {
            item(key = "viewer-provider-title") {
                Text(
                    stringResource(R.string.provider_runtime_vs_seed),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
            }
            items(snapshot.providers, key = { it.id }, contentType = { "viewer-provider" }) { provider ->
                val health = provider.runtimeHealth.uppercase()
                val tone = when (health) {
                    "HEALTHY", "PASS", "READY" -> SourceLabTone.GOOD
                    "BROKEN", "FAILED", "FAIL" -> SourceLabTone.ERROR
                    "DEGRADED", "HELD", "REVIEW" -> SourceLabTone.WARNING
                    else -> SourceLabTone.NEUTRAL
                }
                SourceLabCard(contentPadding = PaddingValues(horizontal = 13.dp, vertical = 11.dp)) {
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Box(Modifier.size(34.dp), contentAlignment = Alignment.Center) {
                            SourceLabIcon(SourceLabIconKind.FARM, Modifier.size(20.dp), SourceLabPrimarySoft)
                        }
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(provider.id.prettyProviderNameLocalized(), fontWeight = FontWeight.Bold)
                            val count = snapshot.sources.count { provider.id in it.providers }
                            Text(
                                stringResource(R.string.registered_memberships_state, count, provider.updateState),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        SourceLabStatusBadge(health.replace('_', ' '), tone)
                    }
                }
            }
        }

        item(key = "viewer-safety") {
            LocalizedSafetyCard()
        }
    }
}

@Composable
private fun LocalizedLiveCard(sync: LocalizedSyncState, onRefresh: () -> Unit) {
    val tone = when (sync) {
        LocalizedSyncState.Loading -> SourceLabTone.ACCENT
        is LocalizedSyncState.Ready -> SourceLabTone.GOOD
        is LocalizedSyncState.Failed -> SourceLabTone.WARNING
    }
    SourceLabCard(tone = tone) {
        when (sync) {
            LocalizedSyncState.Loading -> {
                Row(
                    Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(11.dp),
                ) {
                    CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = SourceLabPrimary)
                    Column(Modifier.weight(1f)) {
                        Text(stringResource(R.string.repository_sync), fontWeight = FontWeight.Bold)
                        Text(
                            stringResource(R.string.reading_farm_state),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            is LocalizedSyncState.Ready -> {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text("Live Farm State", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            Text(
                                stringResource(
                                    R.string.live_sources_summary,
                                    sync.snapshot.cohort,
                                    sync.snapshot.sources.size,
                                    sync.snapshot.targetSize,
                                ),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        SourceLabStatusBadge("LIVE · READ ONLY", SourceLabTone.GOOD)
                    }
                    Text(
                        stringResource(R.string.branch_label, sync.snapshot.branch),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    SourceLabSecondaryButton(
                        text = stringResource(R.string.refresh),
                        onClick = onRefresh,
                        modifier = Modifier.fillMaxWidth(),
                        icon = SourceLabIconKind.REFRESH,
                    )
                }
            }
            is LocalizedSyncState.Failed -> {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    SourceLabStatusBadge("LIVE SYNC UNAVAILABLE", SourceLabTone.WARNING)
                    Text(
                        stringResource(R.string.fallback_checkpoint_message),
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        sync.message,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                    SourceLabSecondaryButton(
                        text = stringResource(R.string.retry),
                        onClick = onRefresh,
                        modifier = Modifier.fillMaxWidth(),
                        icon = SourceLabIconKind.REFRESH,
                    )
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
    val context = LocalContext.current
    val openOwnerGate = {
        context.startActivity(
            android.content.Intent(context, OwnerGateActivity::class.java).addFlags(
                android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    android.content.Intent.FLAG_ACTIVITY_SINGLE_TOP,
            ),
        )
    }

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
                    SourceLabPrimaryButton(
                        text = stringResource(R.string.connect_github_owner),
                        onClick = openOwnerGate,
                        modifier = Modifier.fillMaxWidth(),
                        icon = SourceLabIconKind.LOCK,
                    )
                }
            }
        }
        item {
            Card {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.approval), fontWeight = FontWeight.Bold)
                    Text(stringResource(R.string.approval_locked_supporting))
                    SourceLabSecondaryButton(
                        text = stringResource(R.string.connect_github_owner),
                        onClick = openOwnerGate,
                        modifier = Modifier.fillMaxWidth(),
                        icon = SourceLabIconKind.LOCK,
                    )
                    Text(
                        "Viewer mode remains read-only until Owner/backend authorization succeeds.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
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
    SourceLabCard {
        Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(
                    Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    SourceLabIcon(SourceLabIconKind.LOCK, Modifier.size(18.dp), SourceLabPrimarySoft)
                    Text(stringResource(R.string.safety_boundary), fontWeight = FontWeight.Bold)
                }
                SourceLabStatusBadge("READ ONLY", SourceLabTone.NEUTRAL)
            }
            Text(stringResource(R.string.safety_read_only), style = MaterialTheme.typography.bodySmall)
            Text(stringResource(R.string.safety_pass_not_promote), style = MaterialTheme.typography.bodySmall)
            Text(stringResource(R.string.safety_lkg_exact_approval), style = MaterialTheme.typography.bodySmall)
            Text(stringResource(R.string.safety_stale_fail_closed), style = MaterialTheme.typography.bodySmall)
            Text(stringResource(R.string.safety_no_write_token), style = MaterialTheme.typography.bodySmall)
            Text(stringResource(R.string.safety_no_release_publish), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun LocalizedStatusCard(title: String, status: String, supporting: String) {
    val normalized = status.uppercase()
    val tone = when {
        normalized in setOf("PASS", "READY", "HEALTHY") -> SourceLabTone.GOOD
        "WAITING" in normalized || "REVIEW" in normalized -> SourceLabTone.WARNING
        normalized in setOf("FAIL", "FAILED", "BROKEN") -> SourceLabTone.ERROR
        else -> SourceLabTone.NEUTRAL
    }
    SourceLabCard(tone = tone) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(title, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                SourceLabStatusBadge(status.replace('_', ' '), tone)
            }
            Text(
                supporting,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
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
