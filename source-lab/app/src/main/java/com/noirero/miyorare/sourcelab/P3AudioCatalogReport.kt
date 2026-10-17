package com.noirero.miyorare.sourcelab

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private data class P3AudioCatalogUiState(
    val loading: Boolean = true,
    val snapshot: P3AudioCatalogSnapshot? = null,
    val error: String? = null,
)

@Composable
internal fun P3AudioCatalogReport() {
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf(P3AudioCatalogUiState()) }

    suspend fun refresh() {
        state = state.copy(loading = true, error = null)
        val result = runCatching {
            withContext(Dispatchers.IO) { P3AudioCatalogRepository.loadSnapshot() }
        }
        state = state.copy(
            loading = false,
            snapshot = result.getOrNull() ?: state.snapshot,
            error = result.exceptionOrNull()?.let { it.message ?: it.javaClass.simpleName },
        )
    }

    LaunchedEffect(Unit) { refresh() }

    SourceLabCard(tone = if (state.error != null) SourceLabTone.WARNING else SourceLabTone.NEUTRAL) {
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Miyorare Audio Catalog", fontWeight = FontWeight.Bold)
                    Text(
                        "P3 release catalog authority · separate from Compatibility Farm source counts.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (state.loading) {
                    CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = SourceLabPrimary)
                }
            }

            state.snapshot?.let { catalog ->
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    SourceLabStatusBadge(
                        catalog.releaseEligibility.replace('_', ' '),
                        p3ReleaseTone(catalog.releaseEligibility),
                    )
                    SourceLabStatusBadge("${catalog.runtimes.size} BUILT-IN", SourceLabTone.ACCENT)
                }

                Text(
                    "Source Pack authority · ${catalog.sourcePackCommit}",
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    "Miyorare catalog · ${catalog.miyorareCatalogCommit}",
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    "Hiraukan runtime · ${catalog.hiraukanRuntimeCommit}",
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    "Eligibility reason · ${catalog.releaseEligibilityReason.replace('_', ' ')}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text("Device validation", fontWeight = FontWeight.SemiBold)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        SourceLabStatusBadge(
                            catalog.deviceValidationState.replace('_', ' '),
                            p3DeviceTone(catalog.deviceValidationState),
                        )
                        Text(
                            if (catalog.deviceValidated) "Validated" else "Not validated",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    Text(
                        if (catalog.deviceValidationRequiredForRelease) {
                            "Required for release."
                        } else {
                            "Not required for release; deferred state is not device evidence."
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }

                Text("Built-in runtimes", fontWeight = FontWeight.SemiBold)
                catalog.runtimes.forEach { runtime ->
                    Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
                        Text("${runtime.name} · ${runtime.version}", fontWeight = FontWeight.Medium)
                        Text(
                            runtime.id,
                            fontFamily = FontFamily.Monospace,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }

            state.error?.let { error ->
                SourceLabStatusBadge("P3 CATALOG UNAVAILABLE", SourceLabTone.WARNING)
                Text(
                    error,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    "No Audio Catalog release claim is inferred. Compatibility Farm metrics remain independent and unchanged.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            if (!state.loading) {
                OutlinedButton(onClick = { scope.launch { refresh() } }, modifier = Modifier.fillMaxWidth()) {
                    Text(if (state.error == null) "Refresh Audio Catalog" else "Retry Audio Catalog")
                }
            }
        }
    }
}

private fun p3ReleaseTone(value: String): SourceLabTone = when (value.uppercase()) {
    "ELIGIBLE" -> SourceLabTone.GOOD
    "BLOCKED" -> SourceLabTone.ERROR
    else -> SourceLabTone.NEUTRAL
}

private fun p3DeviceTone(value: String): SourceLabTone = when (value.uppercase()) {
    "VALIDATED" -> SourceLabTone.GOOD
    "DEFERRED_BY_OWNER" -> SourceLabTone.WARNING
    "REQUIRED" -> SourceLabTone.WARNING
    else -> SourceLabTone.NEUTRAL
}
