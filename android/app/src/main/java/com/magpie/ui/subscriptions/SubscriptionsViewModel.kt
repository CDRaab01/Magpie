package com.magpie.ui.subscriptions

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.MuteMerchantRequest
import com.magpie.data.remote.SubscriptionOut
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class SubscriptionsUiState(
    val subscriptions: List<SubscriptionOut> = emptyList(),
    val totalAnnualCostCents: Long = 0,
    val loading: Boolean = true,
    val error: String? = null,
)

@HiltViewModel
class SubscriptionsViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow(SubscriptionsUiState())
    val state: StateFlow<SubscriptionsUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(error = null)
            try {
                val result = api.getSubscriptions()
                _state.value = SubscriptionsUiState(
                    subscriptions = result.subscriptions,
                    totalAnnualCostCents = result.totalAnnualCostCents,
                    loading = false,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    loading = false,
                    error = e.message ?: "Couldn't load subscriptions",
                )
            }
        }
    }

    /** Mark a merchant "not a subscription" (#12). Drop it from the list optimistically so it
     *  disappears immediately; the server keeps it muted for the screen and both sweeps. */
    fun mute(merchant: String) {
        _state.value = _state.value.copy(
            subscriptions = _state.value.subscriptions.filterNot { it.merchant == merchant },
        )
        viewModelScope.launch {
            try {
                api.muteSubscription(MuteMerchantRequest(merchant))
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't hide that")
                load() // put it back if the mute didn't take
            }
        }
    }
}
