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
 * Whether the owner has turned on the app lock (biometric / device credential to open). Opt-in and
 * off by default, so nobody is surprised by a lock; the actual unlock always allows the device PIN
 * as a fallback, so this can never lock anyone out.
 */
@Singleton
class AppLockStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    val enabled: Flow<Boolean> = context.appLockDataStore.data.map { it[ENABLED] ?: false }

    suspend fun setEnabled(value: Boolean) {
        context.appLockDataStore.edit { it[ENABLED] = value }
    }

    private companion object {
        val ENABLED = booleanPreferencesKey("enabled")
    }
}
