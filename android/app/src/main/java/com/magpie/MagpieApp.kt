package com.magpie

import android.app.Application
import com.magpie.data.local.NudgePreferences
import com.magpie.util.NetworkSyncObserver
import com.magpie.util.nudge.ReviewNudgeScheduler
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

@HiltAndroidApp
class MagpieApp : Application() {

    @Inject lateinit var networkSyncObserver: NetworkSyncObserver
    @Inject lateinit var nudgePreferences: NudgePreferences
    @Inject lateinit var reviewNudgeScheduler: ReviewNudgeScheduler

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    override fun onCreate() {
        super.onCreate()
        // Push any offline-queued cash entries as soon as connectivity returns.
        networkSyncObserver.register()
        // "Review your week" nudge: keep the notification channel present, and re-arm the (inexact,
        // non-persistent) alarm on every launch when the owner has opted in — self-heals after a
        // reboot / process death / the OS dropping the alarm.
        reviewNudgeScheduler.ensureChannel()
        appScope.launch {
            if (nudgePreferences.enabled.first()) reviewNudgeScheduler.schedule()
        }
    }
}
