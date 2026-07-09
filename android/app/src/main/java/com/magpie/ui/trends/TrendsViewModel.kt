package com.magpie.ui.trends

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.CategorySummaryItem
import com.magpie.data.remote.MerchantSummaryItem
import com.magpie.data.remote.MonthSummaryOut
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/**
 * The Trends screen state (ROADMAP.md Wave 1 #14) — the three read models the analytics screen
 * draws from: the N-month income/spend/net series, the current month's category breakdown, and
 * its top merchants. Kept a plain data class (not sealed) mirroring [BudgetsUiState] so the
 * silent-refresh + designed-empty-state handling is identical to the sibling screens.
 */
data class TrendsUiState(
    val monthLabel: String = "",
    val history: List<MonthSummaryOut> = emptyList(),
    val categories: List<CategorySummaryItem> = emptyList(),
    val merchants: List<MerchantSummaryItem> = emptyList(),
    val loading: Boolean = true,
    val error: String? = null,
)

private const val HISTORY_MONTHS = 6
private const val TOP_MERCHANTS = 8

@HiltViewModel
class TrendsViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val month: LocalDate = LocalDate.now().withDayOfMonth(1)
    private val monthParam: String = month.toString() // yyyy-MM-dd

    private val _state = MutableStateFlow(
        TrendsUiState(monthLabel = month.format(DateTimeFormatter.ofPattern("MMMM yyyy"))),
    )
    val state: StateFlow<TrendsUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            // Silent refresh (see BudgetsViewModel): don't re-flash the spinner on RefreshOnResume.
            _state.value = _state.value.copy(error = null)
            try {
                val history = api.getHistory(HISTORY_MONTHS).months
                val categories = api.getCategorySummary(monthParam).categories
                val merchants = api.getTopMerchants(monthParam, limit = TOP_MERCHANTS).merchants
                _state.value = _state.value.copy(
                    history = history,
                    categories = categories,
                    merchants = merchants,
                    loading = false,
                )
            } catch (e: Exception) {
                _state.value =
                    _state.value.copy(loading = false, error = e.message ?: "Couldn't load trends")
            }
        }
    }
}
