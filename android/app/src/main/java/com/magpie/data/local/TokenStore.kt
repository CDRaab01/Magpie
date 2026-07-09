package com.magpie.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// Legacy pre-F17 plaintext store — opened once only to purge it, never written again.
private val Context.legacyAuthStore by preferencesDataStore(name = "magpie_auth")

/**
 * Persists the JWT pair **encrypted at rest** (F17) via `EncryptedSharedPreferences` — the suite
 * `PatStore` pattern — because a finance-app session token must not sit in plaintext DataStore.
 *
 * The reactive [accessToken]/[refreshToken] Flows (the auth gate + the refresh authenticator) are
 * preserved as `StateFlow`s, seeded off the main thread since the first `EncryptedSharedPreferences`
 * access generates the Keystore master key. A read/decrypt failure yields `null`, which the app
 * treats as signed-out (→ re-sign-in with Dragonfly), so a corrupted or legacy store never locks
 * anyone out — worst case is one extra sign-in. Existing users' plaintext tokens are wiped on first
 * run of this version and they re-authenticate once.
 */
@Singleton
class TokenStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val prefs by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "magpie_auth_secure",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    private val _access = MutableStateFlow<String?>(null)
    private val _refresh = MutableStateFlow<String?>(null)
    val accessToken: Flow<String?> = _access.asStateFlow()
    val refreshToken: Flow<String?> = _refresh.asStateFlow()

    // Flips true once the first decrypt read lands. The auth gate treats `!initialized` as "unknown"
    // (renders nothing) rather than "signed out" — otherwise the synchronous `null` seed above would
    // read as signed-out and flash the SignIn screen for the ~100ms the Keystore init/decrypt takes.
    private val _initialized = MutableStateFlow(false)
    val initialized: Flow<Boolean> = _initialized.asStateFlow()

    init {
        scope.launch {
            _access.value = readKey(ACCESS)
            _refresh.value = readKey(REFRESH)
            _initialized.value = true
            purgeLegacyPlaintext()
        }
    }

    private fun readKey(key: String): String? =
        runCatching { prefs.getString(key, null) }.getOrNull()?.takeIf { it.isNotBlank() }

    suspend fun save(access: String, refresh: String) = withContext(Dispatchers.IO) {
        prefs.edit().putString(ACCESS, access).putString(REFRESH, refresh).apply()
        _access.value = access
        _refresh.value = refresh
    }

    suspend fun currentAccessToken(): String? = withContext(Dispatchers.IO) { readKey(ACCESS) }

    suspend fun currentRefreshToken(): String? = withContext(Dispatchers.IO) { readKey(REFRESH) }

    suspend fun clear() = withContext(Dispatchers.IO) {
        prefs.edit().clear().apply()
        _access.value = null
        _refresh.value = null
    }

    /** One-time migration: wipe any plaintext tokens left in the old DataStore (pre-F17). */
    private suspend fun purgeLegacyPlaintext() {
        runCatching { context.legacyAuthStore.edit { it.clear() } }
    }

    private companion object {
        const val ACCESS = "access_token"
        const val REFRESH = "refresh_token"
    }
}
