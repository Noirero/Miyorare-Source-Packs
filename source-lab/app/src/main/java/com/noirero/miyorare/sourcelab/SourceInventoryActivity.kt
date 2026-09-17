package com.noirero.miyorare.sourcelab

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
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
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    SourceInventoryScreen(onClose = { finish() })
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
    var state by remember { mutableStateOf(InventoryUiState()) }
    var selectedCanonicalId by rememberSaveable { mutableStateOf<String?>(null) }
    var enrollmentConfirmation by remember { mutableStateOf<InventorySource?>(null) }
    var enrollingCanonical by remember { mutableStateOf<String?>(null) }
    var operationMessage by remember { mutableStateOf<String?>(null) }

    var query by rememberSaveable { mutableStateOf("") }
    var provider by rememberSaveable { mutableStateOf("ALL") }
    var membership by rememberSaveable { mutableStateOf("ALL") }
    var health by rememberSaveable { mutableStateOf("ALL") }
    var language by rememberSaveable { mutableStateOf("ALL") }
    var showAdvancedFilters by rememberSaveable { mutableStateOf(false) }
    val listState = rememberLazyListState()

    suspend fun refreshAll(initial: Boolean) {
        val hadInventory = state.inventory != null
        state = state.copy(
            initialLoading = initial && !hadInventory,
            refreshing = hadInventory,
            inventoryError = null,
            farmError = null,
            ownerError = null,
        )
        coroutineScope {
            val inventoryDeferred = async {
                runCatching { SourceInventoryRepository.loadInventory(context, forceRefresh = true) }
            }
            val farmDeferred = async { runCatching { SourceInventoryRepository.loadFarmMembership() } }
            val ownerDeferred = async { runCatching { SourceLabControlClient.resolveOwnerSession(context) } }

            val inventoryResult = inventoryDeferred.await()
            val farmResult = farmDeferred.await()
            val ownerResult = ownerDeferred.await()
            val previousInventory = state.inventory

            state = state.copy(
                inventory = inventoryResult.getOrNull() ?: previousInventory,
                farm = farmResult.getOrNull() ?: state.farm,
                ownerSession = ownerResult.getOrNull() ?: state.ownerSession,
                initialLoading = false,
                refreshing = false,
                inventoryError = inventoryResult.exceptionOrNull()?.let { it.message ?: it.javaClass.simpleName },
                farmError = farmResult.exceptionOrNull()?.let { it.message ?: it.javaClass.simpleName },
                ownerError = ownerResult.exceptionOrNull()?.let { it.message ?: it.javaClass.simpleName },
            )
        }
    }

    LaunchedEffect(Unit) {
        val cached = SourceInventoryCacheReader.load(context)
        if (cached != null) {
            state = state.copy(
                inventory = cached,
                initialLoading = false,
                refreshing = true,
            )
        }
        refreshAll(initial = cached == null)
    }

    val inventory = state.inventory
    val farmByCanonical = remember(state.farm) {
        state.farm?.sources?.associateBy { it.canonicalId }.orEmpty()
    }
    val selected = remember(inventory, selectedCanonicalId) {
        inventory?.sources?.firstOrNull { it.canonicalId == selectedCanonicalId }
    }

    val confirmSource = enrollmentConfirmation
    if (confirmSource != null && inventory != null && state.farm != null) {
        AlertDialog(
            onDismissRequest = {
                if (enrollingCanonical == null) enrollmentConfirmation = null
            },
            title = { Text("Confirm Add to Farm", fontWeight = FontWeight.Bold) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(confirmSource.displayName, fontWeight = FontWeight.SemiBold)
                    Text(confirmSource.canonicalId, fontFamily = FontFamily.Monospace)
                    Text(
                        "The backend revalidates source identity, inventory commit, Farm state, and Owner capability before any write.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            },
            confirmButton = {
                Button(
                    enabled = enrollingCanonical == null,
                    onClick = {
                        enrollmentConfirmation = null
                        scope.launch {
                            enrollingCanonical = confirmSource.canonicalId
                            operationMessage = null
                            try {
                                val result = SourceLabControlClient.addToFarm(
                                    context = context,
                                    source = confirmSource,
                                    inventory = inventory,
                                    farm = state.farm!!,
                                )
                                operationMessage = "Add to Farm succeeded · run ${result.runId}"
                                refreshAll(initial = false)
                            } catch (error: SourceLabControlException) {
                                operationMessage = "Add to Farm · ${error.reason}"
                            } catch (error: Throwable) {
                                operationMessage = "Add to Farm · ${error.message ?: error.javaClass.simpleName}"
                            } finally {
                                enrollingCanonical = null
                            }
                        }
                    },
                ) { Text("Add to Farm") }
            },
            dismissButton = {
                TextButton(onClick = { enrollmentConfirmation = null }) { Text("Cancel") }
            },
        )
    }

    if (showAdvancedFilters && inventory != null) {
        AdvancedFiltersDialog(
            languages = sourceInventoryLanguageFilters(inventory.sources),
            language = language,
            membership = membership,
            health = health,
            onLanguage = { language = it },
            onMembership = { membership = it },
            onHealth = { health = it },
            onClear = {
                language = "ALL"
                membership = "ALL"
                health = "ALL"
            },
            onDismiss = { showAdvancedFilters = false },
        )
    }

    when {
        inventory == null && state.initialLoading -> InitialInventoryLoading()
        inventory == null -> InventoryUnavailable(
            reason = state.inventoryError ?: "No cached inventory is available.",
            onRetry = { scope.launch { refreshAll(initial = true) } },
        )
        selected != null -> SourceInventoryDetail(
            source = selected,
            farm = farmByCanonical[selected.canonicalId],
            farmStateResolved = state.farm != null,
            ownerSession = state.ownerSession,
            ownerError = state.ownerError,
            enrolling = enrollingCanonical == selected.canonicalId,
            operationMessage = operationMessage,
            onBack = { selectedCanonicalId = null },
            onAddToFarm = { enrollmentConfirmation = selected },
        )
        else -> SourceInventoryList(
            inventory = inventory,
            farm = state.farm,
            farmError = state.farmError,
            inventoryError = state.inventoryError,
            refreshing = state.refreshing,
            operationMessage = operationMessage,
            query = query,
            provider = provider,
            membership = membership,
            health = health,
            language = language,
            listState = listState,
            onQuery = { query = it },
            onProvider = { provider = it },
            onQuickMembership = { membership = it },
            onOpenAdvancedFilters = { showAdvancedFilters = true },
            onClose = onClose,
            onRefresh = { scope.launch { refreshAll(initial = false) } },
            onOpen = { selectedCanonicalId = it.canonicalId },
        )
    }
}

@Composable
private fun InitialInventoryLoading() {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator()
        Spacer(Modifier.height(12.dp))
        Text("Preparing source inventory…")
        Text(
            "This full-screen state is only used when no cached inventory exists yet.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun InventoryUnavailable(reason: String, onRetry: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Source inventory unavailable", color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(reason)
        Spacer(Modifier.height(12.dp))
        Button(onClick = onRetry) { Text("Retry") }
    }
}

internal fun sourceInventoryLanguageFilters(sources: List<InventorySource>): List<String> =
    listOf("ALL") + sources.asSequence()
        .map { it.language }
        .filter { it != "ALL" }
        .distinct()
        .sorted()
        .toList()

@Composable
private fun SourceInventoryList(
    inventory: SourceInventorySnapshot,
    farm: FarmInventorySnapshot?,
    farmError: String?,
    inventoryError: String?,
    refreshing: Boolean,
    operationMessage: String?,
    query: String,
    provider: String,
    membership: String,
    health: String,
    language: String,
    listState: LazyListState,
    onQuery: (String) -> Unit,
    onProvider: (String) -> Unit,
    onQuickMembership: (String) -> Unit,
    onOpenAdvancedFilters: () -> Unit,
    onClose: () -> Unit,
    onRefresh: () -> Unit,
    onOpen: (InventorySource) -> Unit,
) {
    val farmByCanonical = remember(farm) { farm?.sources?.associateBy { it.canonicalId }.orEmpty() }
    val farmResolved = farm != null
    val search = query.trim()
    val visible = remember(inventory, farmByCanonical, search, provider, membership, health, language) {
        inventory.sources.filter { source ->
            val farmSource = farmByCanonical[source.canonicalId]
            val providerMatch = provider == "ALL" || provider.lowercase() in source.providers
            val membershipMatch = when (membership) {
                "IN FARM" -> farmResolved && farmSource != null
                "NOT ENROLLED" -> farmResolved && farmSource == null
                "ISSUES" -> source.needsAttention || farmSource?.runtimeHealth == "BROKEN" ||
                    farmSource?.runtimeHealth == "DEGRADED" || farmSource?.ownerActionRequired == true
                else -> true
            }
            val healthMatch = when (health) {
                "HEALTHY" -> farmSource?.runtimeHealth == "HEALTHY"
                "BROKEN" -> farmSource?.runtimeHealth == "BROKEN"
                "UNKNOWN" -> farmSource?.runtimeHealth.isNullOrBlank() || farmSource.runtimeHealth == "UNKNOWN"
                "NEEDS ATTENTION" -> source.needsAttention || farmSource?.runtimeHealth == "DEGRADED" ||
                    farmSource?.ownerActionRequired == true
                else -> true
            }
            val searchMatch = search.isBlank() ||
                source.displayName.contains(search, ignoreCase = true) ||
                source.canonicalId.contains(search, ignoreCase = true)
            searchMatch && providerMatch && membershipMatch && healthMatch &&
                (language == "ALL" || source.language == language)
        }
    }

    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item(key = "header") {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onClose) { Text("Home") }
                OutlinedButton(onClick = onRefresh, enabled = !refreshing) {
                    if (refreshing) {
                        CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.width(8.dp))
                        Text("Refreshing")
                    } else {
                        Text("Refresh")
                    }
                }
            }
            Text("Sources", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(
                "Manage and inspect ${inventory.sources.size} discovered sources",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (inventory.fromCache) {
                val minutes = inventory.cacheAgeMillis / 60_000L
                Text(
                    if (inventory.staleCacheFallback) "Offline cache · ${minutes}m old" else "Cached data · ${minutes}m old",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (inventory.staleCacheFallback) SourceLabWarning else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        operationMessage?.let { message ->
            item(key = "operation") {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Text(message, Modifier.fillMaxWidth().padding(14.dp), fontWeight = FontWeight.SemiBold)
                }
            }
        }

        if (inventoryError != null || farmError != null) {
            item(key = "refresh-warning") {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF302616))) {
                    Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("Using available data", color = SourceLabWarning, fontWeight = FontWeight.Bold)
                        inventoryError?.let { Text("Inventory refresh: $it", style = MaterialTheme.typography.bodySmall) }
                        farmError?.let { Text("Farm membership: $it", style = MaterialTheme.typography.bodySmall) }
                    }
                }
            }
        }

        item(key = "search-filter") {
            OutlinedTextField(
                value = query,
                onValueChange = onQuery,
                singleLine = true,
                label = { Text("Search sources") },
                placeholder = { Text("Name or canonical ID") },
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(10.dp))
            FilterRow(
                values = listOf("ALL", "KEIYOUSHI", "UMA", "GEKKOUSHI"),
                selected = provider,
                onSelect = onProvider,
            )
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                FilterChip(
                    selected = membership == "IN FARM",
                    onClick = { onQuickMembership(if (membership == "IN FARM") "ALL" else "IN FARM") },
                    label = { Text("In Farm") },
                )
                FilterChip(
                    selected = membership == "ISSUES",
                    onClick = { onQuickMembership(if (membership == "ISSUES") "ALL" else "ISSUES") },
                    label = { Text("Issues") },
                )
                OutlinedButton(onClick = onOpenAdvancedFilters) {
                    Text("More filters")
                }
            }
            Text(
                "${visible.size} matching sources",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        items(
            items = visible,
            key = { it.canonicalId },
            contentType = { "source-row" },
        ) { source ->
            SourceInventoryRow(
                source = source,
                farm = farmByCanonical[source.canonicalId],
                farmResolved = farmResolved,
                onOpen = { onOpen(source) },
            )
        }
    }
}

@Composable
private fun FilterRow(values: List<String>, selected: String, onSelect: (String) -> Unit) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(values, key = { it }) { value ->
            FilterChip(
                selected = selected == value,
                onClick = { onSelect(value) },
                label = { Text(if (value == "ALL") "All" else value.prettyProviderName()) },
            )
        }
    }
}

@Composable
private fun AdvancedFiltersDialog(
    languages: List<String>,
    language: String,
    membership: String,
    health: String,
    onLanguage: (String) -> Unit,
    onMembership: (String) -> Unit,
    onHealth: (String) -> Unit,
    onClear: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("More filters", fontWeight = FontWeight.Bold) },
        text = {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item {
                    Text("Language", fontWeight = FontWeight.SemiBold)
                    FilterRow(languages, language, onLanguage)
                }
                item {
                    Text("Enrollment", fontWeight = FontWeight.SemiBold)
                    FilterRow(listOf("ALL", "IN FARM", "NOT ENROLLED"), membership, onMembership)
                }
                item {
                    Text("Health", fontWeight = FontWeight.SemiBold)
                    FilterRow(listOf("ALL", "HEALTHY", "BROKEN", "UNKNOWN", "NEEDS ATTENTION"), health, onHealth)
                }
            }
        },
        confirmButton = { Button(onClick = onDismiss) { Text("Done") } },
        dismissButton = { TextButton(onClick = onClear) { Text("Clear") } },
    )
}

@Composable
private fun SourceInventoryRow(
    source: InventorySource,
    farm: FarmInventorySourceState?,
    farmResolved: Boolean,
    onOpen: () -> Unit,
) {
    val issue = source.needsAttention || farm?.runtimeHealth == "BROKEN" ||
        farm?.runtimeHealth == "DEGRADED" || farm?.ownerActionRequired == true
    val badgeText = when {
        issue -> "Needs review"
        farm?.runtimeHealth == "HEALTHY" -> "Healthy"
        farm != null -> farm.runtimeHealth.lowercase().replaceFirstChar { it.titlecase() }
        !farmResolved -> "Unknown"
        else -> "Not enrolled"
    }
    val badgeTone = when {
        issue -> SourceLabTone.WARNING
        farm?.runtimeHealth == "HEALTHY" -> SourceLabTone.GOOD
        farm?.runtimeHealth == "BROKEN" -> SourceLabTone.ERROR
        else -> SourceLabTone.NEUTRAL
    }
    val versionCode = source.providers.values.mapNotNull { it.extensionVersionCode }.maxOrNull()

    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onOpen),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Surface(shape = RoundedCornerShape(12.dp), color = SourceLabPrimaryStrong) {
                Text(
                    source.displayName.firstOrNull()?.uppercaseChar()?.toString() ?: "?",
                    Modifier.padding(horizontal = 14.dp, vertical = 11.dp),
                    fontWeight = FontWeight.Bold,
                )
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    source.displayName,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    "${source.language} · ${source.providers.keys.joinToString(" / ") { it.prettyProviderName() }}",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    when {
                        farm != null -> "In Farm${versionCode?.let { " · build $it" }.orEmpty()}"
                        farmResolved -> "Not enrolled${versionCode?.let { " · build $it" }.orEmpty()}"
                        else -> versionCode?.let { "build $it" } ?: "Membership unavailable"
                    },
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.labelMedium,
                )
            }
            SourceLabStatusBadge(badgeText, badgeTone)
        }
    }
}

@Composable
private fun SourceInventoryDetail(
    source: InventorySource,
    farm: FarmInventorySourceState?,
    farmStateResolved: Boolean,
    ownerSession: OwnerAccessSession?,
    ownerError: String?,
    enrolling: Boolean,
    operationMessage: String?,
    onBack: () -> Unit,
    onAddToFarm: () -> Unit,
) {
    val canAdd = farmStateResolved && farm == null && !source.needsAttention &&
        SourceLabAccessPolicy.canPerform(SourceLabControlAction.ADD_TO_FARM, ownerSession)

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "detail-header") {
            TextButton(onClick = onBack) { Text("Back to Sources") }
            Text(source.displayName, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(
                "${source.language} · ${source.providers.keys.joinToString(" / ") { it.prettyProviderName() }}",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(source.canonicalId, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
        }

        operationMessage?.let { message ->
            item(key = "detail-operation") {
                Card { Text(message, Modifier.fillMaxWidth().padding(14.dp), fontWeight = FontWeight.SemiBold) }
            }
        }

        if (source.needsAttention) {
            item(key = "detail-attention") {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF302616))) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("Needs attention", fontWeight = FontWeight.Bold, color = SourceLabWarning)
                        source.attentionReasons.forEach { Text(it) }
                    }
                }
            }
        }

        item(key = "farm-title") { Text("Compatibility Farm", fontWeight = FontWeight.Bold) }
        item(key = "farm-card") {
            FarmSourceCard(source, farm, farmStateResolved)
            if (farmStateResolved && farm == null) {
                Spacer(Modifier.height(10.dp))
                Button(
                    onClick = onAddToFarm,
                    enabled = canAdd && !enrolling,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (enrolling) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    else Text("Add to Farm")
                }
                if (!canAdd) {
                    val reason = when {
                        source.needsAttention -> "Resolve source identity attention before enrollment."
                        ownerError != null -> "Owner capability unavailable: $ownerError"
                        !SourceLabAccessPolicy.canPerform(SourceLabControlAction.ADD_TO_FARM, ownerSession) ->
                            "Backend Add to Farm capability is required."
                        else -> "Farm membership state is not safe for enrollment."
                    }
                    Text(
                        reason,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        item(key = "provider-title") { Text("Provider mappings", fontWeight = FontWeight.Bold) }
        items(source.providers.entries.toList(), key = { it.key }) { (providerName, mapping) ->
            ProviderMappingCard(providerName, mapping)
        }
    }
}

@Composable
private fun ProviderMappingCard(provider: String, mapping: InventoryProviderMapping) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(provider.prettyProviderName(), fontWeight = FontWeight.Bold)
            mapping.displayName?.let { DetailLine("Display name", it) }
            mapping.sourceName?.let { DetailLine("Source name", it) }
            mapping.baseUrl?.let { DetailLine("Base URL", it) }
            mapping.extensionVersionCode?.let { DetailLine("Build", it.toString()) }
            mapping.module?.let { DetailLine("Module", it) }
        }
    }
}

@Composable
private fun FarmSourceCard(
    source: InventorySource,
    farm: FarmInventorySourceState?,
    farmStateResolved: Boolean,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            when {
                !farmStateResolved -> {
                    SourceLabStatusBadge("Membership unknown", SourceLabTone.WARNING)
                    Text("Farm state could not be refreshed, so enrollment is not guessed.")
                }
                farm == null -> {
                    SourceLabStatusBadge("Not enrolled", SourceLabTone.NEUTRAL)
                    Text("Enrollment requires explicit Owner confirmation and server-side validation.")
                    DetailLine("Canonical ID", source.canonicalId)
                }
                else -> {
                    SourceLabStatusBadge(
                        if (farm.runtimeHealth == "HEALTHY") "Healthy" else farm.runtimeHealth,
                        if (farm.runtimeHealth == "HEALTHY") SourceLabTone.GOOD else SourceLabTone.WARNING,
                    )
                    DetailLine("Content profile", farm.contentProfile)
                    DetailLine("Adapter family", farm.adapterFamily)
                    DetailLine("Update state", farm.updateState)
                    DetailLine("Approval state", farm.approvalState)
                    DetailLine("Publish eligible", farm.publishEligible.toString())
                }
            }
        }
    }
}

@Composable
private fun DetailLine(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodySmall)
    }
}

internal fun String.prettyProviderName(): String = when (lowercase()) {
    "all" -> "All"
    "keiyoushi" -> "Keiyoushi"
    "uma" -> "UMA"
    "gekkoushi" -> "Gekkoushi"
    else -> replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
}
