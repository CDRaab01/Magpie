package com.magpie.ui.budgets

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.BudgetCreate
import com.magpie.data.remote.CategoryOut
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** One row of the month-vs-budget view — the category, its cap, and what's been spent against it. */
data class BudgetRow(
    val id: String,
    val categoryName: String,
    val amountCents: Long,
    val spentCents: Long,
)

/** A suggested budget from spending history (#17) — one confirm-per-row draft. */
data class BudgetProposal(
    val categoryId: String,
    val categoryName: String,
    val suggestedAmountCents: Long,
)

data class BudgetsUiState(
    val monthLabel: String = "",
    val rows: List<BudgetRow> = emptyList(),
    // The user's categories, for the add-budget picker.
    val categories: List<CategoryOut> = emptyList(),
    // Trailing-median suggestions for categories with no budget this month (#17) — review, not enter.
    val proposals: List<BudgetProposal> = emptyList(),
    val loading: Boolean = true,
    val error: String? = null,
)

@HiltViewModel
class BudgetsViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val month: LocalDate = LocalDate.now().withDayOfMonth(1)
    private val monthParam: String = month.toString() // yyyy-MM-dd

    private val _state = MutableStateFlow(
        BudgetsUiState(monthLabel = month.format(DateTimeFormatter.ofPattern("MMMM yyyy"))),
    )
    val state: StateFlow<BudgetsUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            // Silent refresh (see BillsViewModel): don't re-flash the spinner on RefreshOnResume.
            _state.value = _state.value.copy(error = null)
            try {
                val budgets = api.listBudgets(monthParam)
                val categories = api.listCategories()
                // Suggestions are nice-to-have — a failed proposals read never blocks the screen.
                val proposals = runCatching { api.budgetProposals(monthParam) }.getOrDefault(emptyList())
                val nameById = categories.associate { it.id to it.name }
                val rows = budgets
                    .map { b ->
                        BudgetRow(
                            id = b.id,
                            categoryName = nameById[b.categoryId] ?: "Unknown",
                            amountCents = b.amount,
                            // actual_cents is spend (negative); show it as positive spent, floored at 0.
                            spentCents = (-b.actualCents).coerceAtLeast(0),
                        )
                    }
                    .sortedBy { it.categoryName }
                // Only propose categories that don't already have a budget this month.
                val budgetedIds = budgets.map { it.categoryId }.toSet()
                val drafts = proposals
                    .filter { it.categoryId !in budgetedIds }
                    .map { BudgetProposal(it.categoryId, it.categoryName, it.suggestedAmountCents) }
                    .sortedByDescending { it.suggestedAmountCents }
                _state.value = _state.value.copy(
                    rows = rows,
                    categories = categories,
                    proposals = drafts,
                    loading = false,
                )
            } catch (e: Exception) {
                _state.value =
                    _state.value.copy(loading = false, error = e.message ?: "Couldn't load budgets")
            }
        }
    }

    fun addBudget(categoryId: String, amountCents: Long) {
        viewModelScope.launch {
            try {
                api.createBudget(BudgetCreate(categoryId, monthParam, amountCents))
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't save budget")
            }
        }
    }

    /** Accept one suggested budget (#17). Drop it from the drafts immediately so the row doesn't
     *  linger while the reload lands. */
    fun acceptProposal(categoryId: String, amountCents: Long) {
        _state.value = _state.value.copy(
            proposals = _state.value.proposals.filterNot { it.categoryId == categoryId },
        )
        addBudget(categoryId, amountCents)
    }
}
