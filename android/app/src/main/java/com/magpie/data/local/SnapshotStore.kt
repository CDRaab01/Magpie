package com.magpie.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.snapshotDataStore by preferencesDataStore(name = "magpie_snapshots")

/**
 * Last-known snapshots of the read screens, so the app degrades to the most recent data offline
 * instead of an error state (the 1.0 offline bar — reads never throw; the tailnet is nearly always
 * reachable, so this is graceful degradation, not a full mirror). Each screen serializes its own
 * assembled view to a JSON string keyed by name; nothing security-sensitive lives here (it is the
 * same aggregates the server would return), so plain DataStore, no encryption.
 */
@Singleton
class SnapshotStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    suspend fun save(key: String, json: String) {
        context.snapshotDataStore.edit { it[stringPreferencesKey(key)] = json }
    }

    suspend fun read(key: String): String? =
        context.snapshotDataStore.data.map { it[stringPreferencesKey(key)] }.first()

    companion object {
        const val HOME = "home"
    }
}
