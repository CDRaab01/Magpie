package com.magpie.ui.transactions

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.TransactionOut
import com.magpie.data.repository.TransactionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed interface TransactionsUiState {
    object Loading : TransactionsUiState
    data class Ready(val transactions: List<TransactionOut>) : TransactionsUiState
    data class Error(val message: String) : TransactionsUiState
}

@HiltViewModel
class TransactionsViewModel @Inject constructor(
    private val transactionRepository: TransactionRepository,
) : ViewModel() {
    private val _state = MutableStateFlow<TransactionsUiState>(TransactionsUiState.Loading)
    val state: StateFlow<TransactionsUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _state.value = TransactionsUiState.Loading
            try {
                _state.value = TransactionsUiState.Ready(transactionRepository.listTransactions())
            } catch (e: Exception) {
                _state.value = TransactionsUiState.Error(e.message ?: "Couldn't load transactions")
            }
        }
    }
}
