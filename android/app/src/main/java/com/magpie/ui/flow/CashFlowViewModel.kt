package com.magpie.ui.flow

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import kotlin.math.abs
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** One outflow of the month's income: a spending category, or what was saved. */
enum class FlowKind { CATEGORY, SAVINGS }

data class CashFlowItem(val label: String, val cents: Long, val kind: FlowKind)

/**
 * The cash-flow Sankey state (ROADMAP.md — Copilot's signature screen): the month's income split
 * into where it went. Income + per-category spend come from the existing summaries; savings is the
 * net. Kept a plain data class like the sibling analytics screens (silent refresh, designed empties).
 */
data class CashFlowUiState(
    val monthLabel: String = "",
    val incomeCents: Long = 0,
    val items: List<CashFlowItem> = emptyList(),
    val loading: Boolean = true,
    val error: String? = null,
)

/** Beyond this, the smallest categories fold into one "Other" flow so the diagram stays legible. */
private const val MAX_CATEGORIES = 7

@HiltViewModel
class CashFlowViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val month: LocalDate = LocalDate.now().withDayOfMonth(1)
    private val monthParam: String = month.toString() // yyyy-MM-dd

    private val _state = MutableStateFlow(
        CashFlowUiState(monthLabel = month.format(DateTimeFormatter.ofPattern("MMMM yyyy"))),
    )
    val state: StateFlow<CashFlowUiState> = _state

    init { load() }

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(error = null)
            try {
                val summary = api.getHistory(1).months.lastOrNull()
                val income = summary?.incomeCents ?: 0L
                val net = summary?.netCents ?: 0L

                val cats = api.getCategorySummary(monthParam).categories
                    .map { CashFlowItem(it.categoryName, abs(it.spendCents), FlowKind.CATEGORY) }
                    .filter { it.cents > 0 }
                    .sortedByDescending { it.cents }

                val items = buildList {
                    if (cats.size > MAX_CATEGORIES) {
                        addAll(cats.take(MAX_CATEGORIES))
                        val other = cats.drop(MAX_CATEGORIES).sumOf { it.cents }
                        if (other > 0) add(CashFlowItem("Other", other, FlowKind.CATEGORY))
                    } else {
                        addAll(cats)
                    }
                    if (net > 0) add(CashFlowItem("Saved", net, FlowKind.SAVINGS))
                }

                _state.value = _state.value.copy(
                    incomeCents = income,
                    items = items,
                    loading = false,
                )
            } catch (e: Exception) {
                _state.value =
                    _state.value.copy(loading = false, error = e.message ?: "Couldn't load cash flow")
            }
        }
    }
}
