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

private val Context.onboardingDataStore by preferencesDataStore(name = "magpie_onboarding")

/**
 * Remembers whether the owner has finished the guided first-run (#33). A plain boolean flag in
 * DataStore — not security-sensitive, so no encryption (unlike [TokenStore]). Gating on this rather
 * than "accounts == 0" lets the flow keep its own multi-step shape past the account-creation step.
 */
@Singleton
class OnboardingStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    val isComplete: Flow<Boolean> =
        context.onboardingDataStore.data.map { it[COMPLETE] ?: false }

    suspend fun setComplete() {
        context.onboardingDataStore.edit { it[COMPLETE] = true }
    }

    private companion object {
        val COMPLETE = booleanPreferencesKey("complete")
    }
}
