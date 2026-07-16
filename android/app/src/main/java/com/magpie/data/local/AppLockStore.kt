package com.magpie.data.local

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.appLockDataStore by preferencesDataStore(name = "magpie_app_lock")

/**
 * Whether the app lock (biometric / device credential to open) is on. **On by default** — a finance
 * app holding full ledger history should lock itself where the device can enforce it (the 1.0 bar).
 * Safe as a default because unlock allows the device PIN as a fallback and **fails open** when the
 * device has neither biometric nor credential enrolled (see MainActivity.promptUnlock), so the
 * default can never lock anyone out; the owner can still turn it off in Settings.
 */
@Singleton
class AppLockStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    val enabled: Flow<Boolean> = context.appLockDataStore.data.map { it[ENABLED] ?: true }

    suspend fun setEnabled(value: Boolean) {
        context.appLockDataStore.edit { it[ENABLED] = value }
    }

    private companion object {
        val ENABLED = booleanPreferencesKey("enabled")
    }
}
