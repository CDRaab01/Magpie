package com.magpie.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.AccountCreate
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.MonthlySummaryOut
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed interface HomeUiState {
    object Loading : HomeUiState
    /** No accounts yet — nothing can be logged until one exists. */
    object NeedsAccount : HomeUiState
    data class Ready(val summary: MonthlySummaryOut, val accounts: List<AccountOut>) : HomeUiState
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
                _state.value = HomeUiState.Ready(summary, accounts)
            } catch (e: Exception) {
                _state.value = HomeUiState.Error(e.message ?: "Couldn't reach Magpie")
            }
        }
    }

    fun createFirstAccount(name: String, institution: String, type: String) {
        viewModelScope.launch {
            try {
                api.createAccount(AccountCreate(name = name, institution = institution, type = type))
                load()
            } catch (e: Exception) {
                _state.value = HomeUiState.Error(e.message ?: "Couldn't create the account")
            }
        }
    }
}
