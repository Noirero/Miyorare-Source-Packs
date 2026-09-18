package com.noirero.miyorare.sourcelab

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch

class SourceInventoryActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceLabPhase1Theme {
                SourceLabAppSurface {
                    SourceInventoryScreen { finish() }
                }
            }
        }
    }
}

private data class InventoryUiState(
    val inventory: SourceInventorySnapshot? = null,
    val farm: FarmInventorySnapshot? = null,
    val ownerSession: OwnerAccessSession? = null,
    val initialLoading: Boolean = true,
    val refreshing: Boolean = false,
    val inventoryError: String? = null,
    val farmError: String? = null,
    val ownerError: String? = null,
)

@Composable
private fun SourceInventoryScreen(onClose: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var ui by remember { mutableStateOf(InventoryUiState()) }
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    var query by rememberSaveable { mutableStateOf("") }
    var provider by rememberSaveable { mutableStateOf("ALL") }
    var quick by rememberSaveable { mutableStateOf("ALL") }
    var language by rememberSaveable { mutableStateOf("ALL") }
    var enrollment by rememberSaveable { mutableStateOf("ALL") }
    var health by rememberSaveable { mutableStateOf("ALL") }
    var showFilters by rememberSaveable { mutableStateOf(false) }
    var confirmAdd by remember { mutableStateOf<InventorySource?>(null) }
    var enrolling by remember { mutableStateOf<String?>(null) }
    var operation by remember { mutableStateOf<String?>(null) }
    val listState = rememberLazyListState()

    suspend fun refresh(initial: Boolean, forceRefresh: Boolean) {
        val hasInventory = ui.inventory != null
        ui = ui.copy(
            initialLoading = initial && !hasInventory,
            refreshing = hasInventory,
            inventoryError = null,
            farmError = null,
            ownerError = null,
        )
        coroutineScope {
            val inventoryJob = async {
                runCatching {
                    SourceInventoryRepository.loadInventory(
                        context = context,
                        forceRefresh = forceRefresh,
                    )
                }
            }
            val farmJob = async { runCatching { SourceInventoryRepository.loadFarmMembership() } }
            val ownerJob = async { runCatching { SourceLabControlClient.resolveOwnerSession(context) } }
            val inventoryResult = inventoryJob.await()
            val farmResult = farmJob.await()
            val ownerResult = ownerJob.await()
            ui = ui.copy(
                inventory = inventoryResult.getOrNull() ?: ui.inventory,
                farm = farmResult.getOrNull(),
                ownerSession = ownerResult.getOrNull(),
                initialLoading = false,
                refreshing = false,
                inventoryError = inventoryResult.exceptionOrNull()?.readableMessage(),
                farmError = farmResult.exceptionOrNull()?.readableMessage(),
                ownerError = ownerResult.exceptionOrNull()?.readableMessage(),
            )
        }
    }

    LaunchedEffect(Unit) {
        val cached = SourceInventoryCacheReader.load(context)
        if (cached != null) {
            ui = ui.copy(inventory = cached, initialLoading = false, refreshing = true)
        }
        refresh(
            initial = cached == null,
            forceRefresh = false,
        )
    }

    val inventory = ui.inventory
    val farmMap = remember(ui.farm) { ui.farm?.sources?.associateBy { it.canonicalId }.orEmpty() }
    val selected = remember(inventory, selectedId) {
        inventory?.sources?.firstOrNull { it.canonicalId == selectedId }
    }

    BackHandler(enabled = selectedId != null) {
        selectedId = null
    }

    if (showFilters && inventory != null) {
        AdvancedFilters(
            languages = sourceInventoryLanguageFilters(inventory.sources),
            language = language,
            enrollment = enrollment,
            health = health,
            onLanguage = { language = it },
            onEnrollment = { enrollment = it },
            onHealth = { health = it },
            onClear = {
                language = "ALL"
                enrollment = "ALL"
                health = "ALL"
            },
            onDismiss = { showFilters = false },
        )
    }

    val pendingAdd = confirmAdd
    if (pendingAdd != null && inventory != null && ui.farm != null && ui.farmError == null) {
        AlertDialog(
            onDismissRequest = { if (enrolling == null) confirmAdd = null },
            title = { Text("Confirm Add to Farm", fontWeight = FontWeight.Bold) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(pendingAdd.displayName, fontWeight = FontWeight.SemiBold)
                    Text(pendingAdd.canonicalId, fontFamily = FontFamily.Monospace)
                    Text(
                        "The backend revalidates identity, inventory/Farm commits and Owner capability before any write.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            },
            confirmButton = {
                Button(
                    enabled = enrolling == null,
                    onClick = {
                        confirmAdd = null
                        scope.launch {
                            enrolling = pendingAdd.canonicalId
                            operation = null
                            try {
                                val result = SourceLabControlClient.addToFarm(context, pendingAdd, inventory, ui.farm!!)
                                operation = "Add to Farm succeeded · run ${result.runId}"
                                refresh(initial = false, forceRefresh = true)
                            } catch (error: SourceLabControlException) {
                                operation = "Add to Farm · ${error.reason}"
                            } catch (error: Throwable) {
                                operation = "Add to Farm · ${error.readableMessage()}"
                            } finally {
                                enrolling = null
                            }
                        }
                    },
                ) { Text("Add to Farm") }
            },
            dismissButton = { TextButton(onClick = { confirmAdd = null }) { Text("Cancel") } },
        )
    }

    when {
        inventory == null && ui.initialLoading -> EmptyCacheLoading()
        inventory == null -> InventoryFailure(ui.inventoryError ?: "No cached inventory is available.") {
            scope.launch { refresh(initial = true, forceRefresh = true) }
        }
        selected != null -> SourceDetail(
            source = selected,
            farm = farmMap[selected.canonicalId],
            farmResolved = ui.farm != null && ui.farmError == null,
            ownerSession = ui.ownerSession,
            ownerError = ui.ownerError,
            enrolling = enrolling == selected.canonicalId,
            operation = operation,
            onBack = { selectedId = null },
            onAdd = { confirmAdd = selected },
        )
        else -> SourcesList(
            inventory = inventory,
            farm = ui.farm,
            refreshing = ui.refreshing,
            inventoryError = ui.inventoryError,
            farmError = ui.farmError,
            operation = operation,
            query = query,
            provider = provider,
            quick = quick,
            language = language,
            enrollment = enrollment,
            health = health,
            listState = listState,
            onQuery = { query = it },
            onProvider = { provider = it },
            onQuick = { quick = it },
            onMoreFilters = { showFilters = true },
            onRefresh = { scope.launch { refresh(initial = false, forceRefresh = true) } },
            onOpen = { selectedId = it.canonicalId },
            onClose = onClose,
        )
    }
}

@Composable
private fun EmptyCacheLoading() {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator()
        Spacer(Modifier.height(12.dp))
        Text("Preparing source inventory…")
        Text(
            "Shown only when this device has no cached inventory yet.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun InventoryFailure(reason: String, retry: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
        Text("Source inventory unavailable", color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.Bold)
        Text(reason)
        Spacer(Modifier.height(12.dp))
        Button(onClick = retry) { Text("Retry") }
    }
}

internal fun sourceInventoryLanguageFilters(sources: List<InventorySource>): List<String> =
    listOf("ALL") + sources.asSequence().map { it.language }.filter { it != "ALL" }.distinct().sorted().toList()

@Composable
private fun SourcesList(
    inventory: SourceInventorySnapshot,
    farm: FarmInventorySnapshot?,
    refreshing: Boolean,
    inventoryError: String?,
    farmError: String?,
    operation: String?,
    query: String,
    provider: String,
    quick: String,
    language: String,
    enrollment: String,
    health: String,
    listState: LazyListState,
    onQuery: (String) -> Unit,
    onProvider: (String) -> Unit,
    onQuick: (String) -> Unit,
    onMoreFilters: () -> Unit,
    onRefresh: () -> Unit,
    onOpen: (InventorySource) -> Unit,
    onClose: () -> Unit,
) {
    val context = LocalContext.current
    val farmMap = remember(farm) { farm?.sources?.associateBy { it.canonicalId }.orEmpty() }
    val farmResolved = farm != null && farmError == null
    val search = query.trim()
    val visible = remember(inventory, farmMap, search, provider, quick, language, enrollment, health, farmResolved) {
        inventory.sources.filter { source ->
            val farmSource = farmMap[source.canonicalId]
            val issue = source.needsAttention || farmSource?.runtimeHealth in setOf("BROKEN", "DEGRADED") ||
                farmSource?.ownerActionRequired == true
            val searchMatch = search.isBlank() || source.displayName.contains(search, true) || source.canonicalId.contains(search, true)
            val providerMatch = provider == "ALL" || provider.lowercase() in source.providers
            val quickMatch = when (quick) {
                "IN FARM" -> farmResolved && farmSource != null
                "ISSUES" -> issue
                else -> true
            }
            val enrollmentMatch = when (enrollment) {
                "IN FARM" -> farmResolved && farmSource != null
                "NOT ENROLLED" -> farmResolved && farmSource == null
                else -> true
            }
            val healthMatch = when (health) {
                "HEALTHY" -> farmSource?.runtimeHealth == "HEALTHY"
                "BROKEN" -> farmSource?.runtimeHealth == "BROKEN"
                "UNKNOWN" -> farmResolved && (farmSource?.runtimeHealth.isNullOrBlank() || farmSource.runtimeHealth == "UNKNOWN")
                "NEEDS ATTENTION" -> issue
                else -> true
            }
            searchMatch && providerMatch && quickMatch && enrollmentMatch && healthMatch &&
                (language == "ALL" || source.language == language)
        }
    }

    Box(Modifier.fillMaxSize()) {
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 16.dp, top = 16.dp, end = 16.dp, bottom = 94.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp),
        ) {
            item(key = "header") {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    SourceLabTopBar(
                        title = "Sources",
                        subtitle = "Manage and inspect source compatibility.",
                        trailing = {
                            SourceLabIconButton(
                                icon = SourceLabIconKind.REFRESH,
                                contentDescription = "Refresh sources",
                                onClick = onRefresh,
                                enabled = !refreshing,
                            )
                        },
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                        SourceLabStatusBadge("${inventory.sources.size} SOURCES", SourceLabTone.ACCENT)
                        if (inventory.fromCache) {
                            val ageMinutes = inventory.cacheAgeMillis / 60_000L
                            SourceLabStatusBadge(
                                if (inventory.staleCacheFallback) "OFFLINE ${ageMinutes}m" else "CACHED ${ageMinutes}m",
                                if (inventory.staleCacheFallback) SourceLabTone.WARNING else SourceLabTone.NEUTRAL,
                            )
                        }
                        if (refreshing) SourceLabStatusBadge("REFRESHING", SourceLabTone.ACCENT)
                    }
                }
            }
            operation?.let { message -> item(key = "operation") { MessageCard(message) } }
            if (inventoryError != null || farmError != null) {
                item(key = "warning") {
                    SourceLabCard(tone = SourceLabTone.WARNING) {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Using available data", color = SourceLabWarning, fontWeight = FontWeight.Bold)
                            inventoryError?.let { Text("Inventory refresh · $it", style = MaterialTheme.typography.bodySmall) }
                            farmError?.let { Text("Farm membership · $it", style = MaterialTheme.typography.bodySmall) }
                        }
                    }
                }
            }
            item(key = "search") {
                SourceLabSearchField(
                    value = query,
                    onValueChange = onQuery,
                    placeholder = "Search source or canonical ID…",
                )
            }
            item(key = "provider-filters") {
                FilterRow(listOf("ALL", "KEIYOUSHI", "UMA", "GEKKOUSHI"), provider, onProvider)
            }
            item(key = "quick-filters") {
                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    item {
                        SourceLabFilterChip(
                            text = "In Farm",
                            selected = quick == "IN FARM",
                            onClick = { onQuick(if (quick == "IN FARM") "ALL" else "IN FARM") },
                        )
                    }
                    item {
                        SourceLabFilterChip(
                            text = "Issues",
                            selected = quick == "ISSUES",
                            onClick = { onQuick(if (quick == "ISSUES") "ALL" else "ISSUES") },
                        )
                    }
                    item {
                        SourceLabFilterChip(
                            text = "More",
                            selected = language != "ALL" || enrollment != "ALL" || health != "ALL",
                            onClick = onMoreFilters,
                        )
                    }
                }
                Spacer(Modifier.height(5.dp))
                Text(
                    "${visible.size} matching sources",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            items(visible, key = { it.canonicalId }, contentType = { "source-card" }) { source ->
                SourceRow(source, farmMap[source.canonicalId], farmResolved) { onOpen(source) }
            }
        }

        SourceLabBottomBar(
            selected = SourceLabDestination.SOURCES,
            onSelect = { destination -> openSourceLabDestination(context, destination) },
            modifier = Modifier.align(Alignment.BottomCenter).padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }
}

@Composable
private fun MessageCard(message: String) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Text(message, Modifier.fillMaxWidth().padding(14.dp), fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun SourceRow(source: InventorySource, farm: FarmInventorySourceState?, farmResolved: Boolean, open: () -> Unit) {
    val issue = source.needsAttention || farm?.runtimeHealth in setOf("BROKEN", "DEGRADED") || farm?.ownerActionRequired == true
    val status = when {
        issue -> "Needs Review" to SourceLabTone.WARNING
        farm?.runtimeHealth == "HEALTHY" -> "Healthy" to SourceLabTone.GOOD
        farm?.runtimeHealth == "BROKEN" -> "Broken" to SourceLabTone.ERROR
        farm != null -> farm.runtimeHealth.replace('_', ' ') to SourceLabTone.NEUTRAL
        farmResolved -> "Not Enrolled" to SourceLabTone.NEUTRAL
        else -> "Unknown" to SourceLabTone.NEUTRAL
    }
    val version = source.providers.values.mapNotNull { it.extensionVersionCode }.maxOrNull()
    SourceLabCard(
        modifier = Modifier.fillMaxWidth().clickable(onClick = open),
        contentPadding = PaddingValues(horizontal = 11.dp, vertical = 10.dp),
        tone = if (issue) SourceLabTone.WARNING else SourceLabTone.NEUTRAL,
    ) {
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Surface(shape = RoundedCornerShape(12.dp), color = SourceLabPrimaryStrong) {
                Box(Modifier.size(42.dp), contentAlignment = Alignment.Center) {
                    Text(
                        source.displayName.firstOrNull()?.uppercaseChar()?.toString() ?: "?",
                        fontWeight = FontWeight.Bold,
                        color = Color.White,
                    )
                }
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    source.displayName,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    "${source.language} · ${source.providers.keys.joinToString(" / ") { providerName(it) }}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    when {
                        farm != null -> "In Farm${version?.let { " · build $it" }.orEmpty()}"
                        farmResolved -> "Not enrolled${version?.let { " · build $it" }.orEmpty()}"
                        else -> version?.let { "Build $it · membership unresolved" } ?: "Membership unresolved"
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            SourceLabStatusBadge(status.first, status.second)
        }
    }
}

@Composable
private fun FilterRow(values: List<String>, selected: String, select: (String) -> Unit) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(values.distinct(), key = { it }) { value ->
            SourceLabFilterChip(
                text = filterLabel(value),
                selected = selected == value,
                onClick = { select(value) },
            )
        }
    }
}

@Composable
private fun AdvancedFilters(
    languages: List<String>,
    language: String,
    enrollment: String,
    health: String,
    onLanguage: (String) -> Unit,
    onEnrollment: (String) -> Unit,
    onHealth: (String) -> Unit,
    onClear: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("More filters", fontWeight = FontWeight.Bold) },
        text = {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { Text("Language", fontWeight = FontWeight.SemiBold); FilterRow(languages, language, onLanguage) }
                item { Text("Enrollment", fontWeight = FontWeight.SemiBold); FilterRow(listOf("ALL", "IN FARM", "NOT ENROLLED"), enrollment, onEnrollment) }
                item { Text("Health", fontWeight = FontWeight.SemiBold); FilterRow(listOf("ALL", "HEALTHY", "BROKEN", "UNKNOWN", "NEEDS ATTENTION"), health, onHealth) }
            }
        },
        confirmButton = { Button(onClick = onDismiss) { Text("Done") } },
        dismissButton = { TextButton(onClick = onClear) { Text("Clear") } },
    )
}

@Composable
private fun SourceDetail(
    source: InventorySource,
    farm: FarmInventorySourceState?,
    farmResolved: Boolean,
    ownerSession: OwnerAccessSession?,
    ownerError: String?,
    enrolling: Boolean,
    operation: String?,
    onBack: () -> Unit,
    onAdd: () -> Unit,
) {
    val canAdd = farmResolved && farm == null && !source.needsAttention &&
        SourceLabAccessPolicy.canPerform(SourceLabControlAction.ADD_TO_FARM, ownerSession)
    val versionBuild = source.providers.values.mapNotNull { it.extensionVersionCode }.maxOrNull()

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "head") {
            SourceLabTopBar(
                title = source.displayName,
                subtitle = source.canonicalId,
                onBack = onBack,
            )
            Spacer(Modifier.height(10.dp))
            SourceLabCard(
                tone = when {
                    source.needsAttention -> SourceLabTone.WARNING
                    farm?.runtimeHealth == "HEALTHY" -> SourceLabTone.GOOD
                    farm?.runtimeHealth in setOf("BROKEN", "DEGRADED") -> SourceLabTone.ERROR
                    else -> SourceLabTone.NEUTRAL
                },
            ) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(shape = RoundedCornerShape(14.dp), color = SourceLabPrimaryStrong) {
                        Box(Modifier.size(54.dp), contentAlignment = Alignment.Center) {
                            Text(
                                source.displayName.firstOrNull()?.uppercaseChar()?.toString() ?: "?",
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold,
                                color = Color.White,
                            )
                        }
                    }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            SourceLabStatusBadge(source.language, SourceLabTone.NEUTRAL)
                            source.providers.keys.take(1).forEach {
                                SourceLabStatusBadge(providerName(it), SourceLabTone.ACCENT)
                            }
                        }
                        Text(
                            "Identity ${source.identityConfidence}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    SourceLabStatusBadge(
                        when {
                            source.needsAttention -> "Needs Review"
                            farm?.runtimeHealth == "HEALTHY" -> "Healthy"
                            farm != null -> farm.runtimeHealth.replace('_', ' ')
                            farmResolved -> "Not Enrolled"
                            else -> "Unknown"
                        },
                        when {
                            source.needsAttention -> SourceLabTone.WARNING
                            farm?.runtimeHealth == "HEALTHY" -> SourceLabTone.GOOD
                            farm?.runtimeHealth in setOf("BROKEN", "DEGRADED") -> SourceLabTone.ERROR
                            else -> SourceLabTone.NEUTRAL
                        },
                    )
                }
            }
        }

        operation?.let { message -> item(key = "operation") { MessageCard(message) } }

        if (source.needsAttention) {
            item(key = "attention") {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF302616))) {
                    Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("Needs attention", color = SourceLabWarning, fontWeight = FontWeight.Bold)
                        source.attentionReasons.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
                    }
                }
            }
        }

        item(key = "current-candidate") {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                SourceLabCard(
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(12.dp),
                ) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Current / Stable", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
                        if (farm?.currentVersion?.isNotEmpty() == true) {
                            farm.currentVersion.entries.take(2).forEach { (providerId, ref) ->
                                Text(
                                    "${providerName(providerId)} · ${shortRef(ref)}",
                                    fontFamily = FontFamily.Monospace,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                        } else if (versionBuild != null) {
                            Text("Build $versionBuild", style = MaterialTheme.typography.bodySmall)
                        } else {
                            Text("No version exposed", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                SourceLabCard(
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(12.dp),
                    tone = if (farm?.ownerActionRequired == true) SourceLabTone.WARNING else SourceLabTone.ACCENT,
                ) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Candidate / Update", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
                        if (farm != null) {
                            Text(
                                farm.updateState.replace('_', ' '),
                                style = MaterialTheme.typography.bodySmall,
                                color = if (farm.ownerActionRequired) SourceLabWarning else SourceLabPrimarySoft,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Text(
                                farm.approvalState.replace('_', ' '),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        } else {
                            Text(
                                if (farmResolved) "Not enrolled" else "Unresolved",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }

        item(key = "identity") {
            DetailCard("Source identity") {
                Detail("Identity confidence", source.identityConfidence)
                versionBuild?.let { Detail("Highest extension build", it.toString()) }
                farm?.let {
                    Detail("Content profile", it.contentProfile)
                    Detail("Adapter family", it.adapterFamily)
                    Detail("Authentication", it.authType)
                }
            }
        }

        item(key = "farm") {
            DetailCard("Compatibility Farm") {
                when {
                    !farmResolved -> SourceLabStatusBadge("Membership unavailable", SourceLabTone.WARNING)
                    farm == null -> SourceLabStatusBadge("Not enrolled", SourceLabTone.NEUTRAL)
                    farm.runtimeHealth == "HEALTHY" -> SourceLabStatusBadge("Healthy", SourceLabTone.GOOD)
                    farm.runtimeHealth in setOf("BROKEN", "DEGRADED") -> SourceLabStatusBadge(farm.runtimeHealth, SourceLabTone.ERROR)
                    else -> SourceLabStatusBadge(farm.runtimeHealth, SourceLabTone.NEUTRAL)
                }
                farm?.let {
                    Detail("Update state", it.updateState)
                    Detail("Approval state", it.approvalState)
                    Detail("Owner action required", it.ownerActionRequired.toString())
                    Detail("Publish eligible", it.publishEligible.toString())
                }
            }
            if (farmResolved && farm == null) {
                Spacer(Modifier.height(10.dp))
                SourceLabPrimaryButton(
                    text = if (enrolling) "Adding to Farm…" else "Add to Farm",
                    onClick = onAdd,
                    enabled = canAdd && !enrolling,
                    modifier = Modifier.fillMaxWidth(),
                    icon = SourceLabIconKind.FARM,
                )
                if (!canAdd) {
                    val reason = when {
                        source.needsAttention -> "Resolve source identity attention before enrollment."
                        ownerError != null -> "Owner capability unavailable: $ownerError"
                        !SourceLabAccessPolicy.canPerform(SourceLabControlAction.ADD_TO_FARM, ownerSession) -> "Backend Add to Farm capability is required."
                        else -> "Farm state is not safe for enrollment."
                    }
                    Text(reason, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }

        farm?.takeIf { it.currentVersion.isNotEmpty() || it.lastKnownGood.isNotEmpty() }?.let { farmState ->
            item(key = "versions") {
                DetailCard("Versions") {
                    farmState.currentVersion.forEach { (providerId, current) ->
                        VersionLine(
                            provider = providerName(providerId),
                            current = current,
                            lastKnownGood = farmState.lastKnownGood[providerId],
                        )
                    }
                }
            }
        }

        farm?.compatibilityBaseline?.let { baseline ->
            item(key = "testing") {
                DetailCard("Compatibility coverage") {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Declared Farm baseline", fontWeight = FontWeight.SemiBold)
                        SourceLabStatusBadge(
                            baseline.status.replace('_', ' '),
                            if (baseline.status == "PASS" || baseline.status == "READY") SourceLabTone.GOOD else SourceLabTone.NEUTRAL,
                        )
                    }
                    if (baseline.capabilities.isEmpty()) {
                        Text("No compatibility capabilities are declared for this source.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    } else {
                        baseline.capabilities.forEach { capability ->
                            CapabilityRow(capability)
                        }
                    }
                }
            }

            item(key = "test-action-boundary") {
                Card(colors = CardDefaults.cardColors(containerColor = SourceLabSurface)) {
                    Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text("Testing", fontWeight = FontWeight.Bold)
                            SourceLabStatusBadge("Farm-wide only", SourceLabTone.ACCENT)
                        }
                        Text(
                            "The current backend exposes Compatibility Farm execution as a farm-wide Owner action, not a per-source test dispatch. Source Lab therefore shows real declared coverage and live Farm state here without fabricating Run Full Test, progress, or PASS/FAIL results.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        farm?.repairPolicy?.let { repair ->
            item(key = "repair") {
                DetailCard("Repair policy") {
                    PolicyLine("Auto diagnose", repair.autoDiagnose)
                    PolicyLine("Safe self-repair", repair.safeSelfRepair)
                    PolicyLine("Keep last known good", repair.keepLastKnownGood)
                    PolicyLine("Validated canonical fallback", repair.validatedCanonicalFallback)
                }
            }
        }

        item(key = "providers-title") { Text("Provider mappings", fontWeight = FontWeight.Bold) }
        items(source.providers.entries.toList(), key = { it.key }) { entry ->
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(providerName(entry.key), fontWeight = FontWeight.Bold)
                        SourceLabStatusBadge(
                            if (entry.value.available) "Available" else "Unavailable",
                            if (entry.value.available) SourceLabTone.GOOD else SourceLabTone.WARNING,
                        )
                    }
                    entry.value.displayName?.let { Detail("Display name", it) }
                    entry.value.sourceName?.let { Detail("Source name", it) }
                    entry.value.baseUrl?.let { Detail("Base URL", it) }
                    entry.value.extensionVersionCode?.let { Detail("Build", it.toString()) }
                    entry.value.module?.let { Detail("Module", it) }
                    entry.value.file?.let { Detail("File", it) }
                }
            }
        }
    }
}

@Composable
private fun DetailCard(title: String, content: @Composable () -> Unit) {
    SourceLabCard {
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

@Composable
private fun VersionLine(provider: String, current: String, lastKnownGood: String?) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(provider, fontWeight = FontWeight.SemiBold)
            Text("Current · ${shortRef(current)}", fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
            lastKnownGood?.let {
                Text("Last known good · ${shortRef(it)}", fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        SourceLabStatusBadge(
            if (lastKnownGood == null || current == lastKnownGood) "Baseline" else "Changed",
            if (lastKnownGood == null || current == lastKnownGood) SourceLabTone.GOOD else SourceLabTone.WARNING,
        )
    }
}

@Composable
private fun CapabilityRow(capability: String) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(capabilityLabel(capability))
        SourceLabStatusBadge("Declared", SourceLabTone.ACCENT)
    }
}

@Composable
private fun PolicyLine(label: String, enabled: Boolean) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label)
        SourceLabStatusBadge(if (enabled) "Enabled" else "Off", if (enabled) SourceLabTone.GOOD else SourceLabTone.NEUTRAL)
    }
}

@Composable
private fun Detail(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodySmall)
    }
}

private fun shortRef(value: String): String = if (value.length > 12) value.take(12) else value

private fun capabilityLabel(value: String): String = when (value.lowercase()) {
    "load" -> "Load"
    "browse" -> "Browse"
    "search" -> "Search"
    "details" -> "Details"
    "chapters" -> "Chapters"
    "content" -> "Pages / Content"
    "authenticate" -> "Login / Authentication"
    "download" -> "Download"
    "reader" -> "Reader"
    else -> value.replace('_', ' ').replaceFirstChar { it.titlecase() }
}

private fun providerName(value: String): String = when (value.lowercase()) {
    "keiyoushi" -> "Keiyoushi"
    "uma" -> "UMA"
    "gekkoushi" -> "Gekkoushi"
    else -> value.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
}

private fun filterLabel(value: String): String = when (value) {
    "ALL" -> "All"
    "KEIYOUSHI", "UMA", "GEKKOUSHI" -> providerName(value)
    else -> value.lowercase().replace('_', ' ').replaceFirstChar { it.titlecase() }
}

private fun Throwable.readableMessage(): String = message ?: javaClass.simpleName
