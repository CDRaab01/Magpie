package com.magpie.util

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
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

/**
 * A short "as of" phrase for the offline read cache's stale indicator: "as of 3:42 PM" when the
 * snapshot was captured today, otherwise "as of Jul 14, 3:42 PM". Time-only for today keeps the
 * common case (a review earlier the same day) compact; the date is added once it's no longer today
 * so a days-old cache reads honestly.
 */
fun formatAsOf(epochMs: Long, zone: ZoneId = ZoneId.systemDefault()): String {
    val dt = Instant.ofEpochMilli(epochMs).atZone(zone)
    val pattern = if (dt.toLocalDate() == LocalDate.now(zone)) "h:mm a" else "MMM d, h:mm a"
    return "as of " + dt.format(DateTimeFormatter.ofPattern(pattern, Locale.US))
}
