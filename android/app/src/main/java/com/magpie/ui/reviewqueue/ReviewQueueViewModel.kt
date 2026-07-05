package com.magpie.ui.reviewqueue

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.TransactionOut
import com.magpie.data.remote.TransactionUpdate
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class ReviewQueueUiState(
    val transactions: List<TransactionOut> = emptyList(),
    // Populated alongside transactions so AI suggestions can show a category *name*, not
    // just an opaque id — the whole point of "shows AI suggestions distinctly" is a human
    // being able to read it at a glance.
    val categoryNamesById: Map<String, String> = emptyMap(),
    val loading: Boolean = true,
    val error: String? = null,
)

@HiltViewModel
class ReviewQueueViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow(ReviewQueueUiState())
    val state: StateFlow<ReviewQueueUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val txns = api.listTransactions(reviewState = "needs_review")
                val categories = api.listCategories().associate { it.id to it.name }
                _state.value = _state.value.copy(
                    transactions = txns,
                    categoryNamesById = categories,
                    loading = false,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    loading = false,
                    error = e.message ?: "Couldn't load the review queue",
                )
            }
        }
    }

    /** Confirming just accepts the draft as-is; a category correction is a separate optional
     * argument so the same action serves both "looks right" and "fix then confirm". */
    fun confirm(transactionId: String, categoryId: String? = null) {
        viewModelScope.launch {
            try {
                api.updateTransaction(
                    transactionId,
                    TransactionUpdate(reviewState = "confirmed", categoryId = categoryId),
                )
                _state.value = _state.value.copy(
                    transactions = _state.value.transactions.filterNot { it.id == transactionId },
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't confirm")
            }
        }
    }
}
