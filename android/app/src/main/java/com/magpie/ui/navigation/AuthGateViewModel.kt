package com.magpie.ui.navigation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.local.TokenStore
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
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
    val isSignedIn: StateFlow<Boolean?> = tokenStore.accessToken
        .map { it != null }
        .stateIn(viewModelScope, SharingStarted.Eagerly, null)
}
