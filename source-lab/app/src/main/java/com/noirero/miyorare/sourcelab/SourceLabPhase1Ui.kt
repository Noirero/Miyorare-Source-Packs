package com.noirero.miyorare.sourcelab

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

internal enum class SourceLabTone {
    GOOD,
    WARNING,
    ERROR,
    ACCENT,
    NEUTRAL,
}

internal val SourceLabBackground = Color(0xFF080C14)
internal val SourceLabSurface = Color(0xFF111826)
internal val SourceLabSurfaceRaised = Color(0xFF182131)
internal val SourceLabPrimary = Color(0xFF7467FF)
internal val SourceLabPrimaryStrong = Color(0xFF5B55F7)
internal val SourceLabGood = Color(0xFF5BE6A8)
internal val SourceLabWarning = Color(0xFFF4BE5B)
internal val SourceLabError = Color(0xFFFF6B74)
internal val SourceLabMuted = Color(0xFFAAB4C4)

@Composable
internal fun SourceLabPhase1Theme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = SourceLabPrimary,
            secondary = Color(0xFF9B7DFF),
            tertiary = SourceLabGood,
            background = SourceLabBackground,
            surface = SourceLabSurface,
            surfaceVariant = SourceLabSurfaceRaised,
            onPrimary = Color.White,
            onBackground = Color(0xFFF5F7FB),
            onSurface = Color(0xFFF5F7FB),
            onSurfaceVariant = SourceLabMuted,
            error = SourceLabError,
        ),
        content = content,
    )
}

@Composable
internal fun SourceLabStatusBadge(
    text: String,
    tone: SourceLabTone,
    modifier: Modifier = Modifier,
) {
    val (container, foreground) = when (tone) {
        SourceLabTone.GOOD -> Color(0xFF123B30) to SourceLabGood
        SourceLabTone.WARNING -> Color(0xFF3A2E16) to SourceLabWarning
        SourceLabTone.ERROR -> Color(0xFF3A1E24) to SourceLabError
        SourceLabTone.ACCENT -> Color(0xFF25215A) to Color(0xFFB9B3FF)
        SourceLabTone.NEUTRAL -> Color(0xFF222B39) to Color(0xFFC1CAD7)
    }
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(999.dp),
        color = container,
    ) {
        Box(Modifier.padding(PaddingValues(horizontal = 10.dp, vertical = 5.dp))) {
            Text(
                text = text,
                color = foreground,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}
