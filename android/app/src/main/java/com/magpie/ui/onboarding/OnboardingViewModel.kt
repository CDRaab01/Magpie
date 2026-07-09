package com.magpie.ui.onboarding

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.local.OnboardingStore
import com.magpie.data.remote.AccountCreate
import com.magpie.data.remote.ApiService
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

@HiltViewModel
class OnboardingViewModel @Inject constructor(
    private val api: ApiService,
    private val onboardingStore: OnboardingStore,
) : ViewModel() {

    // Whether to show the guided first-run. null = not yet known (gate renders nothing, like
    // AuthGateViewModel). Only truly-fresh installs onboard: an existing owner who already has
    // accounts (e.g. updating into this version) is auto-marked complete and never sees it.
    private val _shouldShow = MutableStateFlow<Boolean?>(null)
    val shouldShow: StateFlow<Boolean?> = _shouldShow

    init {
        viewModelScope.launch {
            if (onboardingStore.isComplete.first()) {
                _shouldShow.value = false
                return@launch
            }
            val hasAccounts = runCatching { api.listAccounts().isNotEmpty() }.getOrDefault(false)
            if (hasAccounts) {
                onboardingStore.setComplete()
                _shouldShow.value = false
            } else {
                _shouldShow.value = true
            }
        }
    }

    private val _saving = MutableStateFlow(false)
    val saving: StateFlow<Boolean> = _saving

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    fun addAccount(name: String, institution: String, type: String, last4: String?, onAdded: () -> Unit) {
        viewModelScope.launch {
            _saving.value = true
            _error.value = null
            try {
                api.createAccount(
                    AccountCreate(name = name, institution = institution, type = type, last4 = last4),
                )
                onAdded()
            } catch (e: Exception) {
                _error.value = e.message ?: "Couldn't create the account"
            } finally {
                _saving.value = false
            }
        }
    }

    fun finish(onFinished: () -> Unit) {
        viewModelScope.launch {
            onboardingStore.setComplete()
            _shouldShow.value = false
            onFinished()
        }
    }
}
