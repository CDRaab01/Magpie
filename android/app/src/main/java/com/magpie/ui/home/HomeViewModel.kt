package com.magpie.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.AccountCreate
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.data.remote.UpcomingBillOut
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import java.time.LocalTime
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

private fun greetingForNow(): String = when (LocalTime.now().hour) {
    in 5..11 -> "Good morning"
    in 12..16 -> "Good afternoon"
    else -> "Good evening"
}

sealed interface HomeUiState {
    object Loading : HomeUiState
    /** No accounts yet — nothing can be logged until one exists. */
    object NeedsAccount : HomeUiState
    data class Ready(
        val summary: MonthlySummaryOut,
        val accounts: List<AccountOut>,
        // For the hero (#28): the greeting is resolved here (not in the composable) so the pure
        // Content stays deterministic for screenshot tests; plus how many rows await review and the
        // soonest upcoming bill for the status line.
        val greeting: String = "Hello",
        val reviewCount: Int = 0,
        val nextBill: UpcomingBillOut? = null,
    ) : HomeUiState
    data class Error(val message: String) : HomeUiState
}

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow<HomeUiState>(HomeUiState.Loading)
    val state: StateFlow<HomeUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _state.value = HomeUiState.Loading
            try {
                val accounts = api.listAccounts()
                if (accounts.isEmpty()) {
                    _state.value = HomeUiState.NeedsAccount
                    return@launch
                }
                val now = LocalDate.now()
                val summary = api.monthlySummary(now.year, now.monthValue)
                // Best-effort status inputs for the hero — a hiccup here shouldn't blank the panel.
                val reviewCount =
                    runCatching { api.listTransactions(reviewState = "needs_review").size }
                        .getOrDefault(0)
                val nextBill =
                    runCatching { api.getCashflow().bills.firstOrNull() }.getOrNull()
                _state.value = HomeUiState.Ready(
                    summary, accounts, greetingForNow(), reviewCount, nextBill,
                )
            } catch (e: Exception) {
                _state.value = HomeUiState.Error(e.message ?: "Couldn't reach Magpie")
            }
        }
    }

    fun createFirstAccount(name: String, institution: String, type: String, last4: String?) {
        viewModelScope.launch {
            try {
                api.createAccount(
                    AccountCreate(name = name, institution = institution, type = type, last4 = last4),
                )
                load()
            } catch (e: Exception) {
                _state.value = HomeUiState.Error(e.message ?: "Couldn't create the account")
            }
        }
    }
}
