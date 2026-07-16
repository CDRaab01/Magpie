package com.magpie.widget

import android.content.Context
import androidx.glance.appwidget.updateAll
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Redraws the home-screen widget after the app refreshes its Home snapshot, so the widget shows the
 * same net/safe-to-spend the app just computed instead of staying on "Open Magpie to sync" until
 * Android's slow periodic widget update. Cheap no-op when no widget is placed.
 */
@Singleton
class WidgetRefresher @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    fun refresh() {
        scope.launch {
            runCatching { MagpieWidget().updateAll(context) }
        }
    }
}
