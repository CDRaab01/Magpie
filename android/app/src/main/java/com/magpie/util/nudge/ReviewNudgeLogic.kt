package com.magpie.util.nudge

import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/**
 * Pure scheduling/decision logic for the "Review your week" nudge (Tier W2b) — the habit tier below
 * Magpie's ntfy deviation alerts. A single gentle, opt-in local reminder on Sunday evening (~18:00)
 * prompting the ten-second weekly review. Kept free of Android framework types so the "when should
 * it fire, and should we actually post?" rules are exhaustively unit-testable; the
 * scheduler/receiver are thin wrappers around this.
 *
 * Client-side only — Magpie is tailnet-only, so the nudge fires from a local [android.app.AlarmManager]
 * alarm with no network involved. All gating (opt-in, notifications permission, quiet hours) is
 * re-checked at fire time so a stale alarm can never nag.
 */
object ReviewNudgeLogic {

    /** Local hour-of-day the weekly review nudge fires (Sunday 18:00). */
    const val REVIEW_HOUR: Int = 18

    /** Stable AlarmManager request code + notification id — must not collide with other alarms. */
    const val REQUEST_CODE: Int = 5201

    sealed interface Decision {
        data class Show(val title: String, val text: String) : Decision
        data class Skip(val reason: String) : Decision
    }

    /**
     * True when [hour] (0–23) falls inside the quiet window [quietStart, quietEnd), end-exclusive.
     * The window wraps past midnight when start > end (e.g. 22→7 covers 22,23,0..6). A degenerate
     * start==end window is treated as "no quiet hours" so a mis-set pair can't silence the nudge
     * forever.
     */
    fun isQuietHour(hour: Int, quietStart: Int, quietEnd: Int): Boolean {
        if (quietStart == quietEnd) return false
        return if (quietStart < quietEnd) {
            hour in quietStart until quietEnd
        } else {
            hour >= quietStart || hour < quietEnd
        }
    }

    /**
     * The next Sunday at [REVIEW_HOUR]:00 local time strictly after [nowMillis], as epoch millis.
     * If it is already Sunday but past the fire time (or exactly at it), rolls to the following
     * Sunday. [nowMillis] and [zone] make it deterministic in tests.
     */
    fun nextTriggerMillis(nowMillis: Long, zone: ZoneId): Long {
        val now = LocalDateTime.ofInstant(Instant.ofEpochMilli(nowMillis), zone)
        var candidate = LocalDateTime.of(now.toLocalDate(), LocalTime.of(REVIEW_HOUR, 0))
        // Advance a day at a time until we land on a Sunday that is still strictly in the future.
        while (candidate.dayOfWeek != DayOfWeek.SUNDAY || !candidate.isAfter(now)) {
            candidate = candidate.plusDays(1)
        }
        return candidate.atZone(zone).toInstant().toEpochMilli()
    }

    /**
     * Whether the nudge should actually be posted when its alarm fires, and with what copy.
     *
     * @param enabled the opt-in Settings toggle.
     * @param notificationsAllowed OS-level notification permission/switch is on.
     * @param nowHour the local hour the alarm fired (for the quiet-hours check).
     * @param quietStart / [quietEnd] the quiet-hours window.
     */
    fun decide(
        enabled: Boolean,
        notificationsAllowed: Boolean,
        nowHour: Int,
        quietStart: Int,
        quietEnd: Int,
    ): Decision {
        if (!enabled) return Decision.Skip("disabled")
        if (!notificationsAllowed) return Decision.Skip("notifications-denied")
        if (isQuietHour(nowHour, quietStart, quietEnd)) return Decision.Skip("quiet-hours")
        return Decision.Show(
            title = "Review your week",
            text = "A ten-second look back — tap to catch up on anything that needs a glance.",
        )
    }
}
