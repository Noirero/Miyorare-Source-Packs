package com.noirero.miyorare.sourcelab

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

class SourceLabEntryActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
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
            ) {
                SourceLabEntryScreen {
                    startActivity(Intent(this, LocalizedMainActivity::class.java))
                }
            }
        }
    }
}

@Composable
private fun SourceLabEntryScreen(onContinueViewer: () -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Text(stringResource(R.string.app_name), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(stringResource(R.string.entry_access_subtitle), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item {
            Card {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(stringResource(R.string.public_viewer_title), fontWeight = FontWeight.Bold)
                    Text(stringResource(R.string.public_viewer_supporting))
                    Button(onClick = onContinueViewer, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.continue_as_viewer))
                    }
                }
            }
        }
        item { OwnerLoginCard() }
        item {
            Text(
                stringResource(R.string.owner_controls_fail_closed),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
