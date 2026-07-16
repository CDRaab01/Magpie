package com.magpie.util.nudge

import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import dagger.hilt.android.qualifiers.ApplicationContext
import java.time.ZoneId
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Schedules the weekly "Review your week" nudge via [AlarmManager]. Deliberately uses **inexact**
 * (`setAndAllowWhileIdle`) alarms so no `SCHEDULE_EXACT_ALARM` permission is needed and the reminder
 * stays gentle rather than to-the-second. The alarm re-schedules itself for next Sunday when it
 * fires (see [ReviewNudgeReceiver]); this class (re)arms it on enable, app start, and boot, and
 * cancels it when the owner turns the feature off.
 */
@Singleton
class ReviewNudgeScheduler @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    companion object {
        const val CHANNEL_ID = "magpie_review_nudge"
        private const val CHANNEL_NAME = "Weekly review"
        private const val CHANNEL_DESC = "A gentle Sunday-evening nudge to run your ten-second weekly review"
        const val ACTION = "com.magpie.REVIEW_NUDGE"
    }

    private val alarmManager: AlarmManager?
        get() = context.getSystemService(Context.ALARM_SERVICE) as? AlarmManager

    /** Create the (default-importance) notification channel once; idempotent. */
    fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channel = NotificationChannel(CHANNEL_ID, CHANNEL_NAME, NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = CHANNEL_DESC
            }
            manager.createNotificationChannel(channel)
        }
    }

    /** Arm the nudge for its next occurrence (next Sunday 18:00). Safe to call repeatedly. */
    fun schedule(nowMillis: Long = System.currentTimeMillis()) {
        ensureChannel()
        val am = alarmManager ?: return
        val triggerAt = ReviewNudgeLogic.nextTriggerMillis(nowMillis, ZoneId.systemDefault())
        am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent())
    }

    /** Cancel the scheduled nudge (called when the owner turns the feature off). */
    fun cancel() {
        alarmManager?.cancel(pendingIntent())
    }

    private fun pendingIntent(): PendingIntent {
        val intent = Intent(context, ReviewNudgeReceiver::class.java).apply { action = ACTION }
        return PendingIntent.getBroadcast(
            context,
            ReviewNudgeLogic.REQUEST_CODE,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }
}
