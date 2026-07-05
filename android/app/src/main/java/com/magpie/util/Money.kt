package com.magpie.util

import java.util.Locale
import kotlin.math.abs

/** Signed integer cents -> a display string like "$1,234.56" or "-$12.00". */
fun formatCents(cents: Long): String {
    val sign = if (cents < 0) "-" else ""
    val dollars = abs(cents) / 100.0
    return String.format(Locale.US, "%s$%,.2f", sign, dollars)
}
