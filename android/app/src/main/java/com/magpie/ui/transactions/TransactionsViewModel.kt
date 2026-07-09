package com.magpie.ui.transactions

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.SplitPart
import com.magpie.data.remote.SplitRequest
import com.magpie.data.remote.TransactionOut
import com.magpie.data.repository.TransactionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** The Transactions filter chips (#32) — applied client-side over the loaded list. */
enum class TxnFilter(val label: String) {
    ALL("All"),
    NEEDS_REVIEW("Needs review"),
    SPEND("Spend"),
    INCOME("Income"),
}

sealed interface TransactionsUiState {
    object Loading : TransactionsUiState
    data class Ready(
        val all: List<TransactionOut>,
        val categoryNamesById: Map<String, String>,
        val filter: TxnFilter,
    ) : TransactionsUiState {
        val visible: List<TransactionOut>
            get() = when (filter) {
                TxnFilter.ALL -> all
                TxnFilter.NEEDS_REVIEW -> all.filter { it.reviewState == "needs_review" }
                TxnFilter.SPEND -> all.filter { it.kind == "spend" }
                TxnFilter.INCOME -> all.filter { it.kind == "income" }
            }
    }
    data class Error(val message: String) : TransactionsUiState
}

@HiltViewModel
class TransactionsViewModel @Inject constructor(
    private val transactionRepository: TransactionRepository,
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow<TransactionsUiState>(TransactionsUiState.Loading)
    val state: StateFlow<TransactionsUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            // Silent refresh (see HomeViewModel): initial state is already Loading, so don't re-flash
            // the spinner on RefreshOnResume — keep the list on screen and swap in fresh rows.
            try {
                val transactions = transactionRepository.listTransactions()
                val names = runCatching { api.listCategories().associate { it.id to it.name } }
                    .getOrDefault(emptyMap())
                _state.value = TransactionsUiState.Ready(transactions, names, TxnFilter.ALL)
            } catch (e: Exception) {
                _state.value = TransactionsUiState.Error(e.message ?: "Couldn't load transactions")
            }
        }
    }

    fun setFilter(filter: TxnFilter) {
        val current = _state.value
        if (current is TransactionsUiState.Ready) {
            _state.value = current.copy(filter = filter)
        }
    }

    fun split(transactionId: String, parts: List<SplitPart>) {
        viewModelScope.launch {
            try {
                api.splitTransaction(transactionId, SplitRequest(parts))
            } catch (e: Exception) {
                _state.value = TransactionsUiState.Error(e.message ?: "Couldn't split")
            }
            load()
        }
    }
}
