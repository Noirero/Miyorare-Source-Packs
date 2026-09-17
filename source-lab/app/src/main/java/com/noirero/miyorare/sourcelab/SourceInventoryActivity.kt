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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

class SourceInventoryActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SourceInventoryTheme {
                SourceInventoryScreen(onClose = { finish() })
            }
        }
    }
}

private sealed interface InventoryScreenState {
    data object Loading : InventoryScreenState
    data class Ready(
        val inventory: SourceInventorySnapshot,
        val farm: FarmInventorySnapshot?,
        val farmError: String?,
    ) : InventoryScreenState
    data class Failed(val reason: String) : InventoryScreenState
}

@Composable
private fun SourceInventoryTheme(content: @Composable () -> Unit) {
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
private fun SourceInventoryScreen(onClose: () -> Unit) {
    var refreshKey by remember { mutableIntStateOf(0) }
    var state by remember { mutableStateOf<InventoryScreenState>(InventoryScreenState.Loading) }
    var selected by remember { mutableStateOf<InventorySource?>(null) }

    LaunchedEffect(refreshKey) {
        state = InventoryScreenState.Loading
        state = try {
            val inventory = SourceInventoryRepository.loadInventory()
            val farmResult = runCatching { SourceInventoryRepository.loadFarmMembership() }
            InventoryScreenState.Ready(
                inventory = inventory,
                farm = farmResult.getOrNull(),
                farmError = farmResult.exceptionOrNull()?.message,
            )
        } catch (error: Throwable) {
            InventoryScreenState.Failed(error.message ?: error.javaClass.simpleName)
        }
    }

    when (val current = state) {
        InventoryScreenState.Loading -> InventoryLoading()
        is InventoryScreenState.Failed -> InventoryFailure(current.reason) { refreshKey++ }
        is InventoryScreenState.Ready -> {
            val farmByCanonical = current.farm?.sources?.associateBy { it.canonicalId }.orEmpty()
            selected?.let { source ->
                SourceInventoryDetail(
                    source = source,
                    farm = farmByCanonical[source.canonicalId],
                    farmStateResolved = current.farm != null,
                    onBack = { selected = null },
                )
            } ?: SourceInventoryList(
                inventory = current.inventory,
                farm = current.farm,
                farmError = current.farmError,
                onClose = onClose,
                onRefresh = { refreshKey++ },
                onOpen = { selected = it },
            )
        }
    }
}

@Composable
private fun InventoryLoading() {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator()
        Spacer(Modifier.height(12.dp))
        Text("Loading automatic source inventory…")
    }
}

@Composable
private fun InventoryFailure(reason: String, onRetry: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("SOURCE INVENTORY UNAVAILABLE", color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(reason)
        Spacer(Modifier.height(12.dp))
        Button(onClick = onRetry) { Text("Retry") }
    }
}

@Composable
private fun SourceInventoryList(
    inventory: SourceInventorySnapshot,
    farm: FarmInventorySnapshot?,
    farmError: String?,
    onClose: () -> Unit,
    onRefresh: () -> Unit,
    onOpen: (InventorySource) -> Unit,
) {
    var query by remember { mutableStateOf("") }
    var language by remember { mutableStateOf("ALL") }
    var provider by remember { mutableStateOf("ALL") }
    var membership by remember { mutableStateOf("ALL") }
    var health by remember { mutableStateOf("ALL") }

    val farmByCanonical = farm?.sources?.associateBy { it.canonicalId }.orEmpty()
    val farmResolved = farm != null
    val languages = remember(inventory) {
        listOf("ALL") + inventory.sources.map { it.language }.distinct().sorted()
    }
    val visible = inventory.sources.filter { source ->
        val farmSource = farmByCanonical[source.canonicalId]
        val search = query.trim()
        val providerMatch = provider == "ALL" || provider.lowercase() in source.providers
        val membershipMatch = when (membership) {
            "IN FARM" -> farmResolved && farmSource != null
            "NOT ENROLLED" -> farmResolved && farmSource == null
            else -> true
        }
        val healthMatch = when (health) {
            "HEALTHY" -> farmSource?.runtimeHealth == "HEALTHY"
            "BROKEN" -> farmSource?.runtimeHealth == "BROKEN"
            "UNKNOWN" -> farmSource?.runtimeHealth.isNullOrBlank() || farmSource.runtimeHealth == "UNKNOWN"
            "NEEDS ATTENTION" -> source.needsAttention || farmSource?.runtimeHealth == "DEGRADED" || farmSource?.ownerActionRequired == true
            else -> true
        }
        (search.isBlank() || source.displayName.contains(search, ignoreCase = true) ||
            source.canonicalId.contains(search, ignoreCase = true)) &&
            (language == "ALL" || source.language == language) &&
            providerMatch && membershipMatch && healthMatch
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(onClick = onClose) { Text("Back to Owner") }
                OutlinedButton(onClick = onRefresh) { Text("Refresh") }
            }
            Text("ALL SOURCES", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(
                "Automatic inventory · ${inventory.branch} · discovery is informational only",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        item {
            val summary = inventory.summary(farm?.sources?.map { it.canonicalId }?.toSet().orEmpty())
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text("Inventory", fontWeight = FontWeight.Bold)
                    Text("All Sources ${summary.allSources}")
                    if (farmResolved) {
                        Text("In Farm ${summary.inFarm} · Not Enrolled ${summary.notEnrolled}")
                    } else {
                        Text("Farm membership unavailable", color = MaterialTheme.colorScheme.error)
                    }
                    Text("Needs Attention ${summary.needsAttention}")
                    inventory.providerCommits.forEach { (name, commit) ->
                        Text("${name.uppercase()} ${commit.take(12)}", fontFamily = FontFamily.Monospace)
                    }
                }
            }
        }

        farmError?.let { error ->
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF2A2024))) {
                    Text(
                        "Farm membership could not be refreshed: $error. Inventory remains read-only; membership is not guessed.",
                        Modifier.fillMaxWidth().padding(14.dp),
                    )
                }
            }
        }

        item {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                label = { Text("Search name or canonical ID") },
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(8.dp))
            FilterRow(languages, language) { language = it }
            FilterRow(listOf("ALL", "KEIYOUSHI", "UMA", "GEKKOUSHI"), provider) { provider = it }
            FilterRow(listOf("ALL", "IN FARM", "NOT ENROLLED"), membership) { membership = it }
            FilterRow(listOf("ALL", "HEALTHY", "BROKEN", "UNKNOWN", "NEEDS ATTENTION"), health) { health = it }
            Text("${visible.size} matching sources", style = MaterialTheme.typography.bodySmall)
        }

        items(visible, key = { it.canonicalId }) { source ->
            val farmSource = farmByCanonical[source.canonicalId]
            SourceInventoryRow(source, farmSource, farmResolved) { onOpen(source) }
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
                label = { Text(value) },
            )
        }
    }
    Spacer(Modifier.height(6.dp))
}

@Composable
private fun SourceInventoryRow(
    source: InventorySource,
    farm: FarmInventorySourceState?,
    farmResolved: Boolean,
    onOpen: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onOpen),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.primary) {
                Text(
                    source.displayName.firstOrNull()?.uppercaseChar()?.toString() ?: "?",
                    Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                    fontWeight = FontWeight.Bold,
                )
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(source.displayName, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("${source.language} · ${source.providers.keys.joinToString(" / ") { it.prettyProviderName() }}")
                Text(
                    when {
                        !farmResolved -> "FARM UNKNOWN"
                        farm != null -> "IN FARM · ${farm.runtimeHealth}"
                        else -> "NOT ENROLLED"
                    },
                    style = MaterialTheme.typography.labelMedium,
                    color = if (farm != null) Color(0xFF75E8B0) else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (source.needsAttention || farm?.runtimeHealth == "DEGRADED" || farm?.ownerActionRequired == true) {
                Text("ATTENTION", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun SourceInventoryDetail(
    source: InventorySource,
    farm: FarmInventorySourceState?,
    farmStateResolved: Boolean,
    onBack: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            TextButton(onClick = onBack) { Text("Back to All Sources") }
            Text(source.displayName, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(source.canonicalId, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
            Text("Language ${source.language} · identity ${source.identityConfidence}")
        }

        if (source.needsAttention) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF2A2024))) {
                    Column(Modifier.fillMaxWidth().padding(16.dp)) {
                        Text("NEEDS ATTENTION", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.error)
                        source.attentionReasons.forEach { Text(it) }
                    }
                }
            }
        }

        item { Text("Provider mappings", fontWeight = FontWeight.Bold) }
        items(source.providers.entries.toList(), key = { it.key }) { (provider, mapping) ->
            ProviderMappingCard(provider, mapping)
        }

        item { Text("Compatibility Farm", fontWeight = FontWeight.Bold) }
        item { FarmSourceCard(source, farm, farmStateResolved) }
    }
}

@Composable
private fun ProviderMappingCard(provider: String, mapping: InventoryProviderMapping) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(provider.prettyProviderName(), fontWeight = FontWeight.Bold)
            DetailLine("available", mapping.available.toString())
            mapping.sourceId?.let { DetailLine("sourceId", it.toString()) }
            mapping.sourceName?.let { DetailLine("sourceName", it) }
            mapping.displayName?.let { DetailLine("displayName", it) }
            mapping.module?.let { DetailLine("module", it) }
            mapping.file?.let { DetailLine("file", it) }
            mapping.baseUrl?.let { DetailLine("baseUrl", it) }
            mapping.extensionVersionCode?.let { DetailLine("extensionVersionCode", it.toString()) }
        }
    }
}

@Composable
private fun FarmSourceCard(source: InventorySource, farm: FarmInventorySourceState?, farmStateResolved: Boolean) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            when {
                !farmStateResolved -> {
                    Text("MEMBERSHIP UNKNOWN", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.error)
                    Text("Farm state could not be refreshed, so enrollment is not guessed.")
                }
                farm == null -> {
                    Text("NOT ENROLLED", fontWeight = FontWeight.Bold)
                    Text("Discovery is informational. This source is not automatically trusted, tested, or publish eligible.")
                }
                else -> {
                    Text("IN FARM", fontWeight = FontWeight.Bold, color = Color(0xFF75E8B0))
                    DetailLine("contentProfile", farm.contentProfile)
                    DetailLine("authType", farm.authType)
                    DetailLine("adapterFamily", farm.adapterFamily)
                    DetailLine("runtimeHealth", farm.runtimeHealth)
                    DetailLine("updateState", farm.updateState)
                    DetailLine("approvalState", farm.approvalState)
                    DetailLine("ownerActionRequired", farm.ownerActionRequired.toString())
                    DetailLine("publishEligible", farm.publishEligible.toString())
                    farm.currentVersion.forEach { (provider, sha) ->
                        DetailLine("current ${provider.prettyProviderName()}", sha)
                    }
                    farm.lastKnownGood.forEach { (provider, sha) ->
                        DetailLine("LKG ${provider.prettyProviderName()}", sha)
                    }
                    farm.repairPolicy?.let { policy ->
                        DetailLine(
                            "repairPolicy",
                            "autoDiagnose=${policy.autoDiagnose}, safeSelfRepair=${policy.safeSelfRepair}, keepLKG=${policy.keepLastKnownGood}, canonicalFallback=${policy.validatedCanonicalFallback}",
                        )
                    }
                }
            }
            if (farm == null && farmStateResolved) {
                DetailLine("canonicalId", source.canonicalId)
            }
        }
    }
}

@Composable
private fun DetailLine(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            value,
            fontFamily = if (
                label.contains("SHA", true) || label.startsWith("current") || label.startsWith("LKG")
            ) FontFamily.Monospace else FontFamily.Default,
        )
    }
}

private fun String.prettyProviderName(): String = when (lowercase()) {
    "keiyoushi" -> "Keiyoushi"
    "uma" -> "UMA"
    "gekkoushi" -> "Gekkoushi"
    else -> replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
}
