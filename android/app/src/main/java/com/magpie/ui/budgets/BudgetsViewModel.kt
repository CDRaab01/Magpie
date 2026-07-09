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

data class BudgetsUiState(
    val monthLabel: String = "",
    val rows: List<BudgetRow> = emptyList(),
    // The user's categories, for the add-budget picker.
    val categories: List<CategoryOut> = emptyList(),
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
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val budgets = api.listBudgets(monthParam)
                val categories = api.listCategories()
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
                _state.value =
                    _state.value.copy(rows = rows, categories = categories, loading = false)
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
}
