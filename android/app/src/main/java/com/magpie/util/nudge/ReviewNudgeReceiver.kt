package com.magpie.util.nudge

import android.Manifest
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.magpie.MainActivity
import com.magpie.R
import com.magpie.data.local.NudgePreferences
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking

/**
 * Fires the weekly "Review your week" nudge and re-arms it for next Sunday. Broadcast receivers can't
 * be Hilt-injected, so dependencies come via an [EntryPoint] (mirrors the widget). All gating is
 * honored here — the feature must be enabled, the notifications permission granted, and the fire
 * hour outside quiet hours (see [ReviewNudgeLogic.decide]). Whatever the outcome, the nudge is
 * always re-scheduled so the weekly cadence continues.
 *
 * Tapping the notification deep-links to the review queue via `magpie://review` — the same routing
 * MagpieNavHost already handles for ntfy alerts — so the tap lands exactly where the gentle nudge
 * is pointing.
 */
class ReviewNudgeReceiver : BroadcastReceiver() {

    @EntryPoint
    @InstallIn(SingletonComponent::class)
    interface NudgeEntryPoint {
        fun nudgePreferences(): NudgePreferences
        fun reviewNudgeScheduler(): ReviewNudgeScheduler
    }

    override fun onReceive(context: Context, intent: Intent) {
        val entryPoint = EntryPointAccessors.fromApplication(
            context.applicationContext,
            NudgeEntryPoint::class.java,
        )
        val prefs = entryPoint.nudgePreferences()
        val scheduler = entryPoint.reviewNudgeScheduler()

        // goAsync so the short DataStore reads complete before the process is reclaimed.
        val pending = goAsync()
        try {
            val decision = runBlocking {
                val zone = ZoneId.systemDefault()
                val nowHour = LocalDateTime.ofInstant(Instant.ofEpochMilli(System.currentTimeMillis()), zone).hour
                ReviewNudgeLogic.decide(
                    enabled = prefs.enabled.first(),
                    notificationsAllowed = hasNotificationPermission(context),
                    nowHour = nowHour,
                    quietStart = prefs.quietStartHour.first(),
                    quietEnd = prefs.quietEndHour.first(),
                )
            }
            if (decision is ReviewNudgeLogic.Decision.Show) {
                postNotification(context, decision.title, decision.text)
            }
        } finally {
            // Always re-arm next Sunday, even when this one was suppressed.
            scheduler.schedule()
            pending.finish()
        }
    }

    private fun postNotification(context: Context, title: String, text: String) {
        if (!hasNotificationPermission(context)) return
        val tapIntent = PendingIntent.getActivity(
            context,
            ReviewNudgeLogic.REQUEST_CODE,
            Intent(context, MainActivity::class.java).apply {
                action = Intent.ACTION_VIEW
                data = Uri.parse("magpie://review")
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(context, ReviewNudgeScheduler.CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setContentIntent(tapIntent)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()
        NotificationManagerCompat.from(context).notify(ReviewNudgeLogic.REQUEST_CODE, notification)
    }

    private fun hasNotificationPermission(context: Context): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED
        } else {
            NotificationManagerCompat.from(context).areNotificationsEnabled()
        }
}
