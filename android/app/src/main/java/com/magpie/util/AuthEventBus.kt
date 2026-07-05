package com.magpie.util

import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow

/**
 * App-wide channel for forced-logout events. [com.magpie.data.remote.TokenRefreshAuthenticator]
 * emits here when a refresh token is rejected; the nav graph collects it to bounce the user back
 * to the sign-in screen. Mirrors Spotter/Plate/Cookbook's `AuthEventBus`.
 */
@Singleton
class AuthEventBus @Inject constructor() {
    private val _events = MutableSharedFlow<Unit>(replay = 0, extraBufferCapacity = 1)
    val events: SharedFlow<Unit> = _events.asSharedFlow()

    fun emitLogout() {
        _events.tryEmit(Unit)
    }
}
