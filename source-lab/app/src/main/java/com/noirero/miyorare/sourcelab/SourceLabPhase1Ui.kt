package com.noirero.miyorare.sourcelab

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

internal enum class SourceLabTone {
    GOOD,
    WARNING,
    ERROR,
    ACCENT,
    NEUTRAL,
}

internal val SourceLabBackground = Color(0xFF070B12)
internal val SourceLabSurface = Color(0xFF101722)
internal val SourceLabSurfaceRaised = Color(0xFF172131)
internal val SourceLabPrimary = Color(0xFF7B6DFF)
internal val SourceLabPrimaryStrong = Color(0xFF6558F5)
internal val SourceLabGood = Color(0xFF58D9A6)
internal val SourceLabWarning = Color(0xFFF1B957)
internal val SourceLabError = Color(0xFFFF6F78)
internal val SourceLabMuted = Color(0xFFAAB5C5)

private val SourceLabTypography = Typography(
    headlineLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 30.sp,
        lineHeight = 36.sp,
    ),
    headlineMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 26.sp,
        lineHeight = 32.sp,
    ),
    headlineSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 22.sp,
        lineHeight = 28.sp,
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
        lineHeight = 26.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 17.sp,
        lineHeight = 23.sp,
    ),
    titleSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 15.sp,
        lineHeight = 20.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 16.sp,
        lineHeight = 23.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 14.sp,
        lineHeight = 20.sp,
    ),
    bodySmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 12.sp,
        lineHeight = 17.sp,
    ),
    labelLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 14.sp,
        lineHeight = 18.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 12.sp,
        lineHeight = 16.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        lineHeight = 15.sp,
    ),
)

private val SourceLabShapes = Shapes(
    extraSmall = RoundedCornerShape(10.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(20.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

@Composable
internal fun SourceLabPhase1Theme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = SourceLabPrimary,
            secondary = Color(0xFFA38BFF),
            tertiary = SourceLabGood,
            background = SourceLabBackground,
            surface = SourceLabSurface,
            surfaceVariant = SourceLabSurfaceRaised,
            onPrimary = Color.White,
            onBackground = Color(0xFFF4F7FB),
            onSurface = Color(0xFFF4F7FB),
            onSurfaceVariant = SourceLabMuted,
            outline = Color(0xFF6F7A8D),
            outlineVariant = Color(0xFF2B3544),
            error = SourceLabError,
        ),
        typography = SourceLabTypography,
        shapes = SourceLabShapes,
        content = content,
    )
}

/**
 * Root surface shared by Source Lab activities.
 *
 * Android 15 enforces edge-to-edge for targetSdk 35. Keeping safe-drawing
 * insets here prevents page titles and actions from colliding with status,
 * cutout and navigation bars on small phones and landscape screens.
 */
@Composable
internal fun SourceLabAppSurface(content: @Composable () -> Unit) {
    Surface(
        modifier = Modifier
            .fillMaxSize()
            .safeDrawingPadding(),
        color = MaterialTheme.colorScheme.background,
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
        SourceLabTone.ACCENT -> Color(0xFF29245C) to Color(0xFFC4BEFF)
        SourceLabTone.NEUTRAL -> Color(0xFF222B39) to Color(0xFFC8D0DC)
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
                maxLines = 1,
            )
        }
    }
}
