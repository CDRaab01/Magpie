package com.magpie.util.nudge

import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReviewNudgeLogicTest {

    private val utc = ZoneId.of("UTC")

    private fun millis(y: Int, mo: Int, d: Int, h: Int, mi: Int): Long =
        LocalDateTime.of(y, mo, d, h, mi).toInstant(ZoneOffset.UTC).toEpochMilli()

    private fun asLocal(millis: Long): LocalDateTime =
        LocalDateTime.ofInstant(Instant.ofEpochMilli(millis), utc)

    // ── Next Sunday 18:00 ────────────────────────────────────────────────────

    @Test
    fun `next trigger from a weekday is the coming Sunday at 18_00`() {
        // 2026-07-15 is a Wednesday.
        val now = millis(2026, 7, 15, 10, 0)
        val trigger = asLocal(ReviewNudgeLogic.nextTriggerMillis(now, utc))
        assertEquals(DayOfWeek.SUNDAY, trigger.dayOfWeek)
        assertEquals(millis(2026, 7, 19, 18, 0), ReviewNudgeLogic.nextTriggerMillis(now, utc))
    }

    @Test
    fun `on Sunday before 18_00 it fires that same evening`() {
        // 2026-07-19 is a Sunday.
        val now = millis(2026, 7, 19, 9, 0)
        assertEquals(millis(2026, 7, 19, 18, 0), ReviewNudgeLogic.nextTriggerMillis(now, utc))
    }

    @Test
    fun `on Sunday after 18_00 it rolls to the following Sunday`() {
        val now = millis(2026, 7, 19, 20, 0)
        assertEquals(millis(2026, 7, 26, 18, 0), ReviewNudgeLogic.nextTriggerMillis(now, utc))
    }

    @Test
    fun `exactly Sunday 18_00 rolls forward (strictly future)`() {
        val now = millis(2026, 7, 19, 18, 0)
        assertEquals(millis(2026, 7, 26, 18, 0), ReviewNudgeLogic.nextTriggerMillis(now, utc))
    }

    // ── Quiet hours ──────────────────────────────────────────────────────────

    @Test
    fun `quiet hours wrap past midnight`() {
        assertTrue(ReviewNudgeLogic.isQuietHour(22, 22, 7))
        assertTrue(ReviewNudgeLogic.isQuietHour(23, 22, 7))
        assertTrue(ReviewNudgeLogic.isQuietHour(0, 22, 7))
        assertTrue(ReviewNudgeLogic.isQuietHour(6, 22, 7))
        assertFalse(ReviewNudgeLogic.isQuietHour(7, 22, 7))
        assertFalse(ReviewNudgeLogic.isQuietHour(18, 22, 7))
    }

    @Test
    fun `quiet hours within a single day`() {
        assertTrue(ReviewNudgeLogic.isQuietHour(2, 1, 5))
        assertFalse(ReviewNudgeLogic.isQuietHour(5, 1, 5))
        assertFalse(ReviewNudgeLogic.isQuietHour(0, 1, 5))
    }

    @Test
    fun `equal start and end means no quiet hours`() {
        for (h in 0..23) assertFalse(ReviewNudgeLogic.isQuietHour(h, 9, 9))
    }

    // ── Decision gating ──────────────────────────────────────────────────────

    @Test
    fun `decide shows when enabled, allowed, and outside quiet hours`() {
        val d = ReviewNudgeLogic.decide(
            enabled = true, notificationsAllowed = true, nowHour = 18, quietStart = 22, quietEnd = 7,
        )
        assertTrue(d is ReviewNudgeLogic.Decision.Show)
    }

    @Test
    fun `decide skips when disabled, denied, or in quiet hours`() {
        assertEquals(
            ReviewNudgeLogic.Decision.Skip("disabled"),
            ReviewNudgeLogic.decide(false, true, 18, 22, 7),
        )
        assertEquals(
            ReviewNudgeLogic.Decision.Skip("notifications-denied"),
            ReviewNudgeLogic.decide(true, false, 18, 22, 7),
        )
        assertEquals(
            ReviewNudgeLogic.Decision.Skip("quiet-hours"),
            ReviewNudgeLogic.decide(true, true, 23, 22, 7),
        )
    }
}
