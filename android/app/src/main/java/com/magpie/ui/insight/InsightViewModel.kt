package com.magpie.ui.insight

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.MonthlyInsightOut
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/**
 * The monthly-insight detail (#18) — the full "your month" review behind the Home one-liner:
 * where spending moved vs your usual, how the month landed against budgets, and the AI narrative.
 * Fetched with narrative=true (the Home card uses the fast deterministic aggregate); the server
 * degrades gracefully if the LLM is unavailable.
 */
data class InsightUiState(
    val monthLabel: String = "",
    val insight: MonthlyInsightOut? = null,
    val loading: Boolean = true,
    val error: String? = null,
)

@HiltViewModel
class InsightViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val month: LocalDate = LocalDate.now().withDayOfMonth(1)
    private val monthParam: String = month.toString()

    private val _state = MutableStateFlow(
        InsightUiState(monthLabel = month.format(DateTimeFormatter.ofPattern("MMMM yyyy"))),
    )
    val state: StateFlow<InsightUiState> = _state

    init { load() }

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val insight = api.getMonthlyInsight(monthParam, narrative = true)
                _state.value = _state.value.copy(insight = insight, loading = false)
            } catch (e: Exception) {
                _state.value =
                    _state.value.copy(loading = false, error = e.message ?: "Couldn't load your month")
            }
        }
    }
}
