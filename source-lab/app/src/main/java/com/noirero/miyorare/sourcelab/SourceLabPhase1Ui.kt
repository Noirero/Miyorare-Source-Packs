package com.noirero.miyorare.sourcelab

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

internal enum class SourceLabTone {
    GOOD,
    WARNING,
    ERROR,
    ACCENT,
    NEUTRAL,
}

internal enum class SourceLabIconKind {
    SOURCES,
    FARM,
    REPORTS,
    SETTINGS,
    SEARCH,
    REFRESH,
    BACK,
    CHECK,
    TEST,
    DOCUMENT,
    LOCK,
    USER,
    WARNING,
    CLOSE,
    ARROW_RIGHT,
    DOWNLOAD,
}

internal enum class SourceLabDestination(val label: String, val icon: SourceLabIconKind) {
    SOURCES("Sources", SourceLabIconKind.SOURCES),
    FARM("Farm", SourceLabIconKind.FARM),
    REPORTS("Reports", SourceLabIconKind.REPORTS),
    SETTINGS("Settings", SourceLabIconKind.SETTINGS),
}

internal val SourceLabBackground = Color(0xFF070A12)
internal val SourceLabBackgroundAlt = Color(0xFF0A0E18)
internal val SourceLabSurface = Color(0xFF101623)
internal val SourceLabSurfaceRaised = Color(0xFF151E2D)
internal val SourceLabSurfaceBright = Color(0xFF1A2537)
internal val SourceLabPrimary = Color(0xFF7968FF)
internal val SourceLabPrimaryStrong = Color(0xFF5C6CFF)
internal val SourceLabPrimaryBlue = Color(0xFF3778FF)
internal val SourceLabPrimarySoft = Color(0xFFC2B8FF)
internal val SourceLabGood = Color(0xFF52D89A)
internal val SourceLabWarning = Color(0xFFF2B84B)
internal val SourceLabError = Color(0xFFFF6676)
internal val SourceLabMuted = Color(0xFF9AA8BC)
internal val SourceLabBorder = Color(0xFF263245)

private val SourceLabTypography = Typography(
    headlineLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 32.sp,
        lineHeight = 38.sp,
        letterSpacing = (-0.5).sp,
    ),
    headlineMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 27.sp,
        lineHeight = 33.sp,
        letterSpacing = (-0.35).sp,
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
        fontSize = 16.sp,
        lineHeight = 22.sp,
    ),
    titleSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 14.sp,
        lineHeight = 19.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 15.sp,
        lineHeight = 22.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 13.sp,
        lineHeight = 19.sp,
    ),
    bodySmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 12.sp,
        lineHeight = 17.sp,
    ),
    labelLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 13.sp,
        lineHeight = 18.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 11.sp,
        lineHeight = 15.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 10.sp,
        lineHeight = 14.sp,
    ),
)

private val SourceLabShapes = Shapes(
    extraSmall = RoundedCornerShape(9.dp),
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
            secondary = SourceLabPrimaryBlue,
            tertiary = SourceLabGood,
            background = SourceLabBackground,
            surface = SourceLabSurface,
            surfaceVariant = SourceLabSurfaceRaised,
            onPrimary = Color.White,
            onBackground = Color(0xFFF5F7FC),
            onSurface = Color(0xFFF5F7FC),
            onSurfaceVariant = SourceLabMuted,
            outline = Color(0xFF6C7890),
            outlineVariant = SourceLabBorder,
            error = SourceLabError,
        ),
        typography = SourceLabTypography,
        shapes = SourceLabShapes,
        content = content,
    )
}

/**
 * Shared root for every Source Lab activity.
 *
 * targetSdk 35 uses edge-to-edge by default, so safe-drawing padding remains
 * centralized here. The background is intentionally layered to give Source Lab
 * its own visual identity without depending on third-party assets.
 */
@Composable
internal fun SourceLabAppSurface(content: @Composable () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(
                        Color(0xFF080B14),
                        SourceLabBackground,
                        Color(0xFF060910),
                    ),
                ),
            )
            .safeDrawingPadding(),
    ) {
        content()
    }
}

@Composable
internal fun SourceLabLogo(
    modifier: Modifier = Modifier,
    glow: Boolean = true,
) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(28.dp))
            .background(
                if (glow) {
                    Brush.radialGradient(
                        listOf(
                            Color(0x332F7BFF),
                            Color(0x227B61FF),
                            Color.Transparent,
                        ),
                    )
                } else {
                    Brush.radialGradient(listOf(Color.Transparent, Color.Transparent))
                },
            )
            .padding(10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .semantics { contentDescription = "Miyorare Source Lab flask logo" },
        ) {
            val w = size.width
            val h = size.height
            val outline = Path().apply {
                moveTo(w * 0.38f, h * 0.16f)
                lineTo(w * 0.62f, h * 0.16f)
                lineTo(w * 0.62f, h * 0.34f)
                lineTo(w * 0.78f, h * 0.68f)
                quadraticBezierTo(w * 0.84f, h * 0.82f, w * 0.68f, h * 0.84f)
                lineTo(w * 0.32f, h * 0.84f)
                quadraticBezierTo(w * 0.16f, h * 0.82f, w * 0.22f, h * 0.68f)
                lineTo(w * 0.38f, h * 0.34f)
                close()
            }
            drawPath(
                path = outline,
                brush = Brush.linearGradient(
                    colors = listOf(SourceLabPrimarySoft, SourceLabPrimary, SourceLabPrimaryBlue),
                    start = Offset(w * 0.2f, 0f),
                    end = Offset(w * 0.85f, h),
                ),
                style = Stroke(
                    width = (w * 0.075f).coerceAtLeast(4f),
                    cap = StrokeCap.Round,
                    join = StrokeJoin.Round,
                ),
            )
            val liquid = Path().apply {
                moveTo(w * 0.29f, h * 0.63f)
                quadraticBezierTo(w * 0.40f, h * 0.57f, w * 0.50f, h * 0.63f)
                quadraticBezierTo(w * 0.61f, h * 0.69f, w * 0.72f, h * 0.62f)
                lineTo(w * 0.78f, h * 0.75f)
                quadraticBezierTo(w * 0.80f, h * 0.80f, w * 0.67f, h * 0.80f)
                lineTo(w * 0.33f, h * 0.80f)
                quadraticBezierTo(w * 0.20f, h * 0.80f, w * 0.22f, h * 0.75f)
                close()
            }
            drawPath(
                liquid,
                brush = Brush.horizontalGradient(
                    listOf(Color(0xFF8A5EFF), Color(0xFF3B7BFF)),
                ),
            )
            drawCircle(Color(0xFFCDBEFF), radius = w * 0.035f, center = Offset(w * 0.43f, h * 0.61f))
            drawCircle(Color(0xFF6FA1FF), radius = w * 0.026f, center = Offset(w * 0.58f, h * 0.70f))
        }
    }
}

@Composable
internal fun SourceLabCard(
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(16.dp),
    tone: SourceLabTone = SourceLabTone.NEUTRAL,
    content: @Composable () -> Unit,
) {
    val border = when (tone) {
        SourceLabTone.GOOD -> SourceLabGood.copy(alpha = 0.26f)
        SourceLabTone.WARNING -> SourceLabWarning.copy(alpha = 0.28f)
        SourceLabTone.ERROR -> SourceLabError.copy(alpha = 0.30f)
        SourceLabTone.ACCENT -> SourceLabPrimary.copy(alpha = 0.30f)
        SourceLabTone.NEUTRAL -> SourceLabBorder
    }
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = SourceLabSurfaceRaised),
        border = androidx.compose.foundation.BorderStroke(1.dp, border),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Box(Modifier.fillMaxWidth().padding(contentPadding)) {
            content()
        }
    }
}

@Composable
internal fun SourceLabTopBar(
    title: String,
    subtitle: String? = null,
    modifier: Modifier = Modifier,
    onBack: (() -> Unit)? = null,
    trailing: (@Composable () -> Unit)? = null,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (onBack != null) {
            SourceLabIconButton(
                icon = SourceLabIconKind.BACK,
                contentDescription = "Back",
                onClick = onBack,
            )
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                title,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            subtitle?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        trailing?.invoke()
    }
}

@Composable
internal fun SourceLabIconButton(
    icon: SourceLabIconKind,
    contentDescription: String,
    onClick: () -> Unit,
    enabled: Boolean = true,
    modifier: Modifier = Modifier,
) {
    val source = remember { MutableInteractionSource() }
    Box(
        modifier = modifier
            .size(44.dp)
            .clip(RoundedCornerShape(13.dp))
            .background(SourceLabSurfaceRaised)
            .border(1.dp, SourceLabBorder, RoundedCornerShape(13.dp))
            .clickable(
                enabled = enabled,
                interactionSource = source,
                indication = null,
                onClick = onClick,
            )
            .semantics { this.contentDescription = contentDescription },
        contentAlignment = Alignment.Center,
    ) {
        SourceLabIcon(
            kind = icon,
            modifier = Modifier.size(20.dp),
            tint = if (enabled) MaterialTheme.colorScheme.onSurface else SourceLabMuted.copy(alpha = 0.45f),
        )
    }
}

@Composable
internal fun SourceLabStatusBadge(
    text: String,
    tone: SourceLabTone,
    modifier: Modifier = Modifier,
) {
    val (container, foreground) = when (tone) {
        SourceLabTone.GOOD -> Color(0xFF102F28) to SourceLabGood
        SourceLabTone.WARNING -> Color(0xFF332817) to SourceLabWarning
        SourceLabTone.ERROR -> Color(0xFF331A22) to SourceLabError
        SourceLabTone.ACCENT -> Color(0xFF24204F) to SourceLabPrimarySoft
        SourceLabTone.NEUTRAL -> Color(0xFF202938) to Color(0xFFC3CCDA)
    }
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(999.dp),
        color = container,
        border = androidx.compose.foundation.BorderStroke(1.dp, foreground.copy(alpha = 0.22f)),
    ) {
        Row(
            Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Box(
                Modifier
                    .size(5.dp)
                    .clip(RoundedCornerShape(999.dp))
                    .background(foreground),
            )
            Text(
                text = text,
                color = foreground,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
internal fun SourceLabPrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    icon: SourceLabIconKind? = null,
) {
    val shape = RoundedCornerShape(14.dp)
    val source = remember { MutableInteractionSource() }
    val brush = if (enabled) {
        Brush.horizontalGradient(listOf(Color(0xFF765BFF), Color(0xFF3978FF)))
    } else {
        Brush.horizontalGradient(listOf(Color(0xFF2B3140), Color(0xFF2B3140)))
    }
    Row(
        modifier = modifier
            .defaultMinSize(minHeight = 52.dp)
            .clip(shape)
            .background(brush)
            .border(1.dp, if (enabled) Color(0x557A8CFF) else SourceLabBorder, shape)
            .clickable(
                enabled = enabled,
                interactionSource = source,
                indication = null,
                onClick = onClick,
            )
            .padding(horizontal = 16.dp, vertical = 14.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        icon?.let {
            SourceLabIcon(it, Modifier.size(18.dp), Color.White)
            Spacer(Modifier.width(8.dp))
        }
        Text(
            text,
            color = if (enabled) Color.White else SourceLabMuted.copy(alpha = 0.65f),
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
internal fun SourceLabSecondaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    icon: SourceLabIconKind? = null,
) {
    val shape = RoundedCornerShape(14.dp)
    val source = remember { MutableInteractionSource() }
    Row(
        modifier = modifier
            .defaultMinSize(minHeight = 50.dp)
            .clip(shape)
            .background(SourceLabSurfaceRaised)
            .border(1.dp, SourceLabBorder, shape)
            .clickable(
                enabled = enabled,
                interactionSource = source,
                indication = null,
                onClick = onClick,
            )
            .padding(horizontal = 15.dp, vertical = 13.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        icon?.let {
            SourceLabIcon(
                it,
                Modifier.size(18.dp),
                if (enabled) MaterialTheme.colorScheme.onSurface else SourceLabMuted.copy(alpha = 0.45f),
            )
            Spacer(Modifier.width(8.dp))
        }
        Text(
            text,
            color = if (enabled) MaterialTheme.colorScheme.onSurface else SourceLabMuted.copy(alpha = 0.45f),
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
internal fun SourceLabDangerButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    val shape = RoundedCornerShape(14.dp)
    val source = remember { MutableInteractionSource() }
    Row(
        modifier = modifier
            .defaultMinSize(minHeight = 50.dp)
            .clip(shape)
            .background(if (enabled) Color(0xFF4A1F29) else SourceLabSurfaceRaised)
            .border(1.dp, if (enabled) SourceLabError.copy(alpha = 0.45f) else SourceLabBorder, shape)
            .clickable(
                enabled = enabled,
                interactionSource = source,
                indication = null,
                onClick = onClick,
            )
            .padding(horizontal = 15.dp, vertical = 13.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text,
            color = if (enabled) SourceLabError else SourceLabMuted.copy(alpha = 0.45f),
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
internal fun SourceLabMetricCard(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    tone: SourceLabTone = SourceLabTone.NEUTRAL,
    supporting: String? = null,
) {
    val valueColor = when (tone) {
        SourceLabTone.GOOD -> SourceLabGood
        SourceLabTone.WARNING -> SourceLabWarning
        SourceLabTone.ERROR -> SourceLabError
        SourceLabTone.ACCENT -> SourceLabPrimarySoft
        SourceLabTone.NEUTRAL -> MaterialTheme.colorScheme.onSurface
    }
    SourceLabCard(
        modifier = modifier,
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 11.dp),
        tone = tone,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text(
                value,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = valueColor,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                label,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            supporting?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
internal fun SourceLabFilterChip(
    text: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(999.dp)
    val source = remember { MutableInteractionSource() }
    Row(
        modifier = modifier
            .clip(shape)
            .background(if (selected) Color(0xFF2B2661) else SourceLabSurfaceRaised)
            .border(
                1.dp,
                if (selected) SourceLabPrimary.copy(alpha = 0.6f) else SourceLabBorder,
                shape,
            )
            .clickable(interactionSource = source, indication = null, onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text,
            color = if (selected) SourceLabPrimarySoft else MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.SemiBold,
        )
    }
}

@Composable
internal fun SourceLabSearchField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String = "Search sources…",
) {
    val shape = RoundedCornerShape(14.dp)
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(shape)
            .background(SourceLabSurfaceRaised)
            .border(1.dp, SourceLabBorder, shape)
            .padding(horizontal = 13.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        SourceLabIcon(
            kind = SourceLabIconKind.SEARCH,
            modifier = Modifier.size(18.dp),
            tint = SourceLabMuted,
        )
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = Modifier.weight(1f),
            textStyle = MaterialTheme.typography.bodyMedium.copy(
                color = MaterialTheme.colorScheme.onSurface,
            ),
            singleLine = true,
            cursorBrush = Brush.linearGradient(listOf(SourceLabPrimary, SourceLabPrimaryBlue)),
            decorationBox = { inner ->
                Box {
                    if (value.isBlank()) {
                        Text(
                            placeholder,
                            style = MaterialTheme.typography.bodyMedium,
                            color = SourceLabMuted.copy(alpha = 0.75f),
                        )
                    }
                    inner()
                }
            },
        )
        if (value.isNotBlank()) {
            Box(
                Modifier
                    .size(28.dp)
                    .clip(RoundedCornerShape(9.dp))
                    .clickable { onValueChange("") },
                contentAlignment = Alignment.Center,
            ) {
                SourceLabIcon(SourceLabIconKind.CLOSE, Modifier.size(14.dp), SourceLabMuted)
            }
        }
    }
}

@Composable
internal fun SourceLabBottomBar(
    selected: SourceLabDestination,
    onSelect: (SourceLabDestination) -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = Color(0xF2131925),
        border = androidx.compose.foundation.BorderStroke(1.dp, SourceLabBorder),
        shadowElevation = 6.dp,
    ) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            SourceLabDestination.entries.forEach { destination ->
                val active = destination == selected
                val source = remember(destination) { MutableInteractionSource() }
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(14.dp))
                        .background(if (active) Color(0xFF23204B) else Color.Transparent)
                        .clickable(
                            interactionSource = source,
                            indication = null,
                            onClick = { onSelect(destination) },
                        )
                        .padding(vertical = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(3.dp),
                ) {
                    SourceLabIcon(
                        destination.icon,
                        Modifier.size(19.dp),
                        if (active) SourceLabPrimarySoft else SourceLabMuted,
                    )
                    Text(
                        destination.label,
                        style = MaterialTheme.typography.labelSmall,
                        color = if (active) SourceLabPrimarySoft else SourceLabMuted,
                        fontWeight = if (active) FontWeight.Bold else FontWeight.Medium,
                    )
                }
            }
        }
    }
}

internal fun openSourceLabDestination(context: Context, destination: SourceLabDestination) {
    val target = when (destination) {
        SourceLabDestination.SOURCES -> SourceInventoryActivity::class.java
        SourceLabDestination.FARM -> {
            if (SourceLabAccessPolicy.evaluate(SourceLabOwnerSessionStore.get()).canControl) {
                AutonomousOwnerControlActivity::class.java
            } else {
                LocalizedMainActivity::class.java
            }
        }
        SourceLabDestination.REPORTS -> ReportsActivity::class.java
        SourceLabDestination.SETTINGS -> SettingsActivity::class.java
    }
    if (context::class.java != target) {
        context.startActivity(Intent(context, target))
    }
}

@Composable
internal fun SourceLabIcon(
    kind: SourceLabIconKind,
    modifier: Modifier = Modifier,
    tint: Color = MaterialTheme.colorScheme.onSurface,
) {
    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height
        val stroke = Stroke(
            width = (w.coerceAtMost(h) * 0.09f).coerceAtLeast(1.8f),
            cap = StrokeCap.Round,
            join = StrokeJoin.Round,
        )
        when (kind) {
            SourceLabIconKind.SOURCES -> {
                drawRoundRect(
                    color = tint,
                    topLeft = Offset(w * 0.12f, h * 0.16f),
                    size = Size(w * 0.76f, h * 0.68f),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(w * 0.12f),
                    style = stroke,
                )
                drawLine(tint, Offset(w * 0.28f, h * 0.38f), Offset(w * 0.72f, h * 0.38f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.28f, h * 0.60f), Offset(w * 0.64f, h * 0.60f), strokeWidth = stroke.width, cap = StrokeCap.Round)
            }
            SourceLabIconKind.FARM, SourceLabIconKind.TEST -> {
                val p = Path().apply {
                    moveTo(w * 0.40f, h * 0.12f)
                    lineTo(w * 0.60f, h * 0.12f)
                    lineTo(w * 0.60f, h * 0.34f)
                    lineTo(w * 0.78f, h * 0.72f)
                    quadraticBezierTo(w * 0.83f, h * 0.84f, w * 0.68f, h * 0.86f)
                    lineTo(w * 0.32f, h * 0.86f)
                    quadraticBezierTo(w * 0.17f, h * 0.84f, w * 0.22f, h * 0.72f)
                    lineTo(w * 0.40f, h * 0.34f)
                    close()
                }
                drawPath(p, tint, style = stroke)
                drawLine(tint, Offset(w * 0.31f, h * 0.64f), Offset(w * 0.69f, h * 0.64f), strokeWidth = stroke.width, cap = StrokeCap.Round)
            }
            SourceLabIconKind.REPORTS, SourceLabIconKind.DOCUMENT -> {
                drawRoundRect(
                    tint,
                    topLeft = Offset(w * 0.19f, h * 0.10f),
                    size = Size(w * 0.62f, h * 0.80f),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(w * 0.09f),
                    style = stroke,
                )
                drawLine(tint, Offset(w * 0.32f, h * 0.40f), Offset(w * 0.68f, h * 0.40f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.32f, h * 0.58f), Offset(w * 0.68f, h * 0.58f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.32f, h * 0.74f), Offset(w * 0.56f, h * 0.74f), strokeWidth = stroke.width, cap = StrokeCap.Round)
            }
            SourceLabIconKind.SETTINGS -> {
                drawCircle(tint, w * 0.16f, Offset(w * 0.5f, h * 0.5f), style = stroke)
                repeat(8) { index ->
                    val a = Math.toRadians((index * 45.0))
                    val inner = Offset(
                        (w * 0.5f + kotlin.math.cos(a).toFloat() * w * 0.28f),
                        (h * 0.5f + kotlin.math.sin(a).toFloat() * h * 0.28f),
                    )
                    val outer = Offset(
                        (w * 0.5f + kotlin.math.cos(a).toFloat() * w * 0.40f),
                        (h * 0.5f + kotlin.math.sin(a).toFloat() * h * 0.40f),
                    )
                    drawLine(tint, inner, outer, strokeWidth = stroke.width, cap = StrokeCap.Round)
                }
            }
            SourceLabIconKind.SEARCH -> {
                drawCircle(tint, w * 0.28f, Offset(w * 0.43f, h * 0.43f), style = stroke)
                drawLine(tint, Offset(w * 0.63f, h * 0.63f), Offset(w * 0.86f, h * 0.86f), strokeWidth = stroke.width, cap = StrokeCap.Round)
            }
            SourceLabIconKind.REFRESH -> {
                drawArc(tint, -40f, 285f, false, topLeft = Offset(w * 0.16f, h * 0.16f), size = Size(w * 0.68f, h * 0.68f), style = stroke)
                val p = Path().apply {
                    moveTo(w * 0.75f, h * 0.12f)
                    lineTo(w * 0.88f, h * 0.20f)
                    lineTo(w * 0.76f, h * 0.30f)
                }
                drawPath(p, tint, style = stroke)
            }
            SourceLabIconKind.BACK -> {
                drawLine(tint, Offset(w * 0.78f, h * 0.50f), Offset(w * 0.22f, h * 0.50f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.22f, h * 0.50f), Offset(w * 0.45f, h * 0.26f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.22f, h * 0.50f), Offset(w * 0.45f, h * 0.74f), strokeWidth = stroke.width, cap = StrokeCap.Round)
            }
            SourceLabIconKind.CHECK -> {
                drawLine(tint, Offset(w * 0.18f, h * 0.53f), Offset(w * 0.40f, h * 0.74f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.40f, h * 0.74f), Offset(w * 0.84f, h * 0.25f), strokeWidth = stroke.width, cap = StrokeCap.Round)
            }
            SourceLabIconKind.LOCK -> {
                drawRoundRect(tint, Offset(w * 0.20f, h * 0.42f), Size(w * 0.60f, h * 0.44f), androidx.compose.ui.geometry.CornerRadius(w * 0.10f), style = stroke)
                drawArc(tint, 180f, 180f, false, Offset(w * 0.32f, h * 0.12f), Size(w * 0.36f, h * 0.48f), style = stroke)
            }
            SourceLabIconKind.USER -> {
                drawCircle(tint, w * 0.16f, Offset(w * 0.5f, h * 0.30f), style = stroke)
                drawArc(tint, 205f, 130f, false, Offset(w * 0.18f, h * 0.48f), Size(w * 0.64f, h * 0.44f), style = stroke)
            }
            SourceLabIconKind.WARNING -> {
                val p = Path().apply {
                    moveTo(w * 0.50f, h * 0.12f)
                    lineTo(w * 0.90f, h * 0.84f)
                    lineTo(w * 0.10f, h * 0.84f)
                    close()
                }
                drawPath(p, tint, style = stroke)
                drawLine(tint, Offset(w * 0.50f, h * 0.36f), Offset(w * 0.50f, h * 0.60f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawCircle(tint, stroke.width * 0.6f, Offset(w * 0.50f, h * 0.73f))
            }
            SourceLabIconKind.CLOSE -> {
                drawLine(tint, Offset(w * 0.24f, h * 0.24f), Offset(w * 0.76f, h * 0.76f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.76f, h * 0.24f), Offset(w * 0.24f, h * 0.76f), strokeWidth = stroke.width, cap = StrokeCap.Round)
            }
            SourceLabIconKind.ARROW_RIGHT -> {
                drawLine(tint, Offset(w * 0.18f, h * 0.50f), Offset(w * 0.80f, h * 0.50f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.80f, h * 0.50f), Offset(w * 0.58f, h * 0.28f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.80f, h * 0.50f), Offset(w * 0.58f, h * 0.72f), strokeWidth = stroke.width, cap = StrokeCap.Round)
            }
            SourceLabIconKind.DOWNLOAD -> {
                drawLine(tint, Offset(w * 0.50f, h * 0.14f), Offset(w * 0.50f, h * 0.64f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.50f, h * 0.64f), Offset(w * 0.31f, h * 0.46f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.50f, h * 0.64f), Offset(w * 0.69f, h * 0.46f), strokeWidth = stroke.width, cap = StrokeCap.Round)
                drawLine(tint, Offset(w * 0.18f, h * 0.84f), Offset(w * 0.82f, h * 0.84f), strokeWidth = stroke.width, cap = StrokeCap.Round)
            }
        }
    }
}
