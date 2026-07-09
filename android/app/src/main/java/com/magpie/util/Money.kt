package com.magpie.util

import java.util.Locale
import kotlin.math.abs

/** Signed integer cents -> a display string like "$1,234.56" or "-$12.00". */
fun formatCents(cents: Long): String {
    val sign = if (cents < 0) "-" else ""
    val dollars = abs(cents) / 100.0
    return String.format(Locale.US, "%s$%,.2f", sign, dollars)
}

/**
 * Compact, whole-dollar money for headline stat tiles (V1.md Tier 4 #30) — "$1,320", "-$4,500",
 * "$0". Cents belong in detail views, not the front-page tiles where "$0.00" was wrapping across
 * three lines; rounding to the nearest dollar keeps the value short enough to fit one line.
 */
fun formatCentsCompact(cents: Long): String {
    val sign = if (cents < 0) "-" else ""
    val dollars = Math.round(abs(cents) / 100.0)
    return String.format(Locale.US, "%s$%,d", sign, dollars)
}
