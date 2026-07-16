package com.magpie.util.nudge

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.magpie.data.local.NudgePreferences
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking

/**
 * Alarms don't survive a reboot, so re-arm the weekly review nudge on boot when the feature is
 * enabled. Uses an [EntryPoint] since receivers can't be Hilt-injected.
 */
class NudgeBootReceiver : BroadcastReceiver() {

    @EntryPoint
    @InstallIn(SingletonComponent::class)
    interface BootEntryPoint {
        fun nudgePreferences(): NudgePreferences
        fun reviewNudgeScheduler(): ReviewNudgeScheduler
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val entryPoint = EntryPointAccessors.fromApplication(
            context.applicationContext,
            BootEntryPoint::class.java,
        )
        val pending = goAsync()
        try {
            val enabled = runBlocking { entryPoint.nudgePreferences().enabled.first() }
            if (enabled) entryPoint.reviewNudgeScheduler().schedule()
        } finally {
            pending.finish()
        }
    }
}
