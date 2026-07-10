package com.magpie.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import design.pulse.ui.theme.PulseAccent
import design.pulse.ui.theme.PulseChannel
import design.pulse.ui.theme.PulseDataTypography
import design.pulse.ui.theme.PulseTheme
import design.pulse.ui.theme.PulseRed
import design.pulse.ui.theme.PulseRedDeep
import design.pulse.ui.theme.Spacing
import design.pulse.ui.theme.LocalDataTypography
import design.pulse.ui.theme.LocalSpacing
import design.pulse.ui.theme.darkChannel
import design.pulse.ui.theme.darkGreenChannel
import design.pulse.ui.theme.darkAmberChannel
import design.pulse.ui.theme.darkVioletChannel
import design.pulse.ui.theme.darkPulseStructure
import design.pulse.ui.theme.lightChannel
import design.pulse.ui.theme.lightGreenChannel
import design.pulse.ui.theme.lightAmberChannel
import design.pulse.ui.theme.lightVioletChannel
import design.pulse.ui.theme.lightPulseStructure

/**
 * Magpie's semantic layer over PULSE — the money channel map (ARCHITECTURE.md §"Android design"):
 *  - money:       teal   — the hero/primary-action channel (Magpie's lead accent)
 *  - underBudget: green  — income, under-budget, in-band/auto-filed states
 *  - needsReview: amber  — the review queue, deviation warnings
 *  - overBudget:  red    — over-budget, out-of-band deviations
 * Structure (hairlines/panels/glow) and the hero gradient ride along so screens have one stop.
 *
 * The red channel isn't a PulseAccent (Pulse only defines channel triples for its four accent
 * hues) — it's built here from the same PulseRed/PulseRedDeep values already proven as Pulse's
 * M3 error scheme, rather than inventing new untested colors. Channel *semantics* belong app-side
 * per Pulse's own rule; only the raw hues are shared.
 */
@Immutable
data class MagpieColors(
    val money: PulseChannel,
    val underBudget: PulseChannel,
    val needsReview: PulseChannel,
    val overBudget: PulseChannel,
    /** violet — the AI voice: category drafts and the monthly insight, visually distinct from
     * the deterministic teal/green/amber channels so "the model suggested this" reads at a glance
     * (ARCHITECTURE.md §"Android design"; #31's violet-for-AI tail). */
    val aiVoice: PulseChannel,
    val hairline: Color,
    val hairlineStrong: Color,
    val panel: Color,
    val panelHigh: Color,
    val glow: Color,
    /** Indigo -> teal -> green, Magpie's lead voice (the "magpie" hero gradient in Pulse). */
    val heroGradient: Brush,
)

private fun darkRedChannel() = PulseChannel(PulseRed, Color(0xFF4A1414), Color(0xFF3D0202))
private fun lightRedChannel() = PulseChannel(PulseRedDeep, Color(0xFFFBE0E0), Color(0xFFFFFFFF))

private fun magpieColors(dark: Boolean): MagpieColors {
    val structure = if (dark) darkPulseStructure(PulseAccent.Teal) else lightPulseStructure(PulseAccent.Teal)
    return MagpieColors(
        money = if (dark) darkChannel(PulseAccent.Teal) else lightChannel(PulseAccent.Teal),
        underBudget = if (dark) darkGreenChannel() else lightGreenChannel(),
        needsReview = if (dark) darkAmberChannel() else lightAmberChannel(),
        overBudget = if (dark) darkRedChannel() else lightRedChannel(),
        aiVoice = if (dark) darkVioletChannel() else lightVioletChannel(),
        hairline = structure.hairline,
        hairlineStrong = structure.hairlineStrong,
        panel = structure.panel,
        panelHigh = structure.panelHigh,
        glow = structure.glow,
        heroGradient = structure.heroGradient,
    )
}

val LocalMagpieColors = staticCompositionLocalOf { magpieColors(dark = true) }

@Composable
fun MagpieTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    PulseTheme(darkTheme = darkTheme, accent = PulseAccent.Teal) {
        CompositionLocalProvider(
            LocalMagpieColors provides magpieColors(darkTheme),
        ) {
            content()
        }
    }
}

/** Convenience accessors mirroring `MaterialTheme.*`. */
object MagpieTheme {
    val colors: MagpieColors
        @Composable @ReadOnlyComposable get() = LocalMagpieColors.current
    val dataType: PulseDataTypography
        @Composable @ReadOnlyComposable get() = LocalDataTypography.current
    val spacing: Spacing
        @Composable @ReadOnlyComposable get() = LocalSpacing.current
}
