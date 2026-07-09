package com.magpie.ui.navigation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.local.TokenStore
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn

/**
 * Gates the nav graph on whether a Magpie session exists. `null` = not yet known (DataStore's
 * first read hasn't landed); once [SuiteAuthManager] saves a session, this Flow re-emits and
 * the UI recomposes into the main graph — no explicit post-sign-in navigation call needed.
 */
@HiltViewModel
class AuthGateViewModel @Inject constructor(
    tokenStore: TokenStore,
) : ViewModel() {
    val isSignedIn: StateFlow<Boolean?> =
        combine(tokenStore.initialized, tokenStore.accessToken) { initialized, token ->
            // Stay `null` (nav shows nothing) until the encrypted store's first read lands, so a
            // signed-in user never flashes the SignIn screen while the token is still decrypting.
            if (!initialized) null else token != null
        }.stateIn(viewModelScope, SharingStarted.Eagerly, null)
}
