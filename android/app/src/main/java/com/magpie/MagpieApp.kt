package com.magpie

import android.app.Application
import com.magpie.util.NetworkSyncObserver
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

@HiltAndroidApp
class MagpieApp : Application() {

    @Inject lateinit var networkSyncObserver: NetworkSyncObserver

    override fun onCreate() {
        super.onCreate()
        // Push any offline-queued cash entries as soon as connectivity returns.
        networkSyncObserver.register()
    }
}
