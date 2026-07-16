package com.magpie.data.local

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.nudgeDataStore by preferencesDataStore(name = "magpie_review_nudge")

/**
 * Settings for the "Review your week" nudge (Tier W2b): whether it's on, and the quiet-hours window
 * during which it stays silent. **Opt-in: [enabled] defaults to false** — Magpie never nudges until
 * the owner turns it on. Quiet hours default to 22:00–07:00 so a fire time that lands overnight is
 * suppressed unless the owner widens the window.
 */
@Singleton
class NudgePreferences @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    val enabled: Flow<Boolean> = context.nudgeDataStore.data.map { it[ENABLED] ?: false }

    /** Start of quiet hours (hour-of-day, 0–23). No nudge posts at/after this until [quietEndHour]. */
    val quietStartHour: Flow<Int> = context.nudgeDataStore.data.map { it[QUIET_START] ?: DEFAULT_QUIET_START }

    /** End of quiet hours (hour-of-day, 0–23). The nudge resumes at this hour. */
    val quietEndHour: Flow<Int> = context.nudgeDataStore.data.map { it[QUIET_END] ?: DEFAULT_QUIET_END }

    suspend fun setEnabled(value: Boolean) {
        context.nudgeDataStore.edit { it[ENABLED] = value }
    }

    suspend fun setQuietHours(startHour: Int, endHour: Int) {
        context.nudgeDataStore.edit {
            it[QUIET_START] = startHour.coerceIn(0, 23)
            it[QUIET_END] = endHour.coerceIn(0, 23)
        }
    }

    private companion object {
        const val DEFAULT_QUIET_START = 22
        const val DEFAULT_QUIET_END = 7
        val ENABLED = booleanPreferencesKey("enabled")
        val QUIET_START = intPreferencesKey("quiet_start_hour")
        val QUIET_END = intPreferencesKey("quiet_end_hour")
    }
}
