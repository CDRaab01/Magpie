package com.magpie.security

import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * The runtime locked/unlocked state of the app lock (a finance app should not sit open on a lock
 * screen). Held app-scoped so [com.magpie.MainActivity] can lock on backgrounding and the Compose
 * tree can gate on it. Enabling/disabling the feature lives in [com.magpie.data.local.AppLockStore].
 */
@Singleton
class AppLock @Inject constructor() {
    private val _locked = MutableStateFlow(false)
    val locked: StateFlow<Boolean> = _locked.asStateFlow()

    fun lock() { _locked.value = true }
    fun unlock() { _locked.value = false }
}
