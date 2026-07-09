package com.magpie.ui.reviewqueue

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.RuleCreate
import com.magpie.data.remote.TransactionOut
import com.magpie.data.remote.TransactionUpdate
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class ReviewQueueUiState(
    val transactions: List<TransactionOut> = emptyList(),
    // The full category list backs the correction picker (seeded + the user's own); the
    // derived name map lets an AI suggestion show a readable *name* rather than an opaque id.
    val categories: List<CategoryOut> = emptyList(),
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
                val categories = api.listCategories()
                _state.value = _state.value.copy(
                    transactions = txns,
                    categories = categories,
                    categoryNamesById = categories.associate { it.id to it.name },
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

    /**
     * The single confirm/correct action behind the whole queue. Every argument past the id is
     * "leave untouched" when null (matching the server's PATCH semantics), so one function
     * serves all three flows:
     *  - `confirm(id)` — accept the draft as-is (the one-tap happy path),
     *  - `confirm(id, categoryId)` — accept the AI suggestion or pick/assign a category,
     *  - `confirm(id, categoryId, kind)` — also correct the rare sign-ambiguous kind.
     * The server re-validates the sign invariant when `kind` is supplied, so a bad kind change
     * surfaces as an error here rather than silently corrupting the ledger — on failure the row
     * stays in the queue.
     *
     * `ruleMatcher` powers the "make this a rule" growth loop (#22): when the human corrects a
     * row and asks to always file this merchant this way, we create a `merchant_category` rule
     * (matcher → categoryId) *after* the confirm, so future transactions from that merchant
     * auto-file and skip the queue. Only meaningful alongside a `categoryId`.
     */
    fun confirm(
        transactionId: String,
        categoryId: String? = null,
        kind: String? = null,
        ruleMatcher: String? = null,
    ) {
        viewModelScope.launch {
            try {
                api.updateTransaction(
                    transactionId,
                    TransactionUpdate(
                        reviewState = "confirmed",
                        categoryId = categoryId,
                        kind = kind,
                    ),
                )
                // The row is confirmed regardless of what happens with the optional rule below.
                _state.value = _state.value.copy(
                    error = null,
                    transactions = _state.value.transactions.filterNot { it.id == transactionId },
                )
                if (ruleMatcher != null && categoryId != null) {
                    api.createRule(
                        RuleCreate(
                            type = "merchant_category",
                            matcher = ruleMatcher,
                            categoryId = categoryId,
                        ),
                    )
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't confirm")
            }
        }
    }
}
