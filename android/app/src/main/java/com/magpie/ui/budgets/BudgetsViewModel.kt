package com.magpie.ui.budgets

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.BudgetCreate
import com.magpie.data.remote.BudgetUpdate
import com.magpie.data.remote.CategoryAnalysisOut
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.CoachPlanOut
import com.magpie.data.remote.GoalOut
import com.magpie.data.remote.GoalUpsert
import com.magpie.data.remote.NetProjectionOut
import com.magpie.data.remote.ProposedCutOut
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** One row of the month-vs-budget view — the category, its cap, what's been spent, and (when the
 *  coach status loads) the pace context: projection, daily allowance, and status. */
data class BudgetRow(
    val id: String,
    val categoryId: String,
    val categoryName: String,
    val amountCents: Long,
    val spentCents: Long,
    val projectedCents: Long? = null,
    val dailyAllowanceCents: Long? = null,
    val paceStatus: String? = null, // early | on_track | watch | over_pace | over; null = no coach
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
    // AI budget coach: goal + projection (deterministic), coaching prose (LLM, optional).
    val goal: GoalOut? = null,
    val net: NetProjectionOut? = null,
    val daysLeft: Int? = null,
    val uncategorizedMtdCents: Long = 0,
    val coachHeadline: String? = null,
    val coachCoaching: String? = null,
    // The savings plan ("how do I get there?") — computed on request, never stored server-side.
    val plan: CoachPlanOut? = null,
    val planLoading: Boolean = false,
    // Per-category deep-dive sheet.
    val analysis: CategoryAnalysisOut? = null,
    val analysisLoading: Boolean = false,
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
                // Suggestions and coach status are nice-to-have — failures never block the screen.
                val proposals = runCatching { api.budgetProposals(monthParam) }.getOrDefault(emptyList())
                val coach = runCatching { api.coachStatus(narrative = false) }.getOrNull()
                val paceByCategory = coach?.budgets.orEmpty().associateBy { it.categoryId }

                val nameById = categories.associate { it.id to it.name }
                val rows = budgets
                    .map { b ->
                        val pace = paceByCategory[b.categoryId]
                        BudgetRow(
                            id = b.id,
                            categoryId = b.categoryId,
                            categoryName = nameById[b.categoryId] ?: "Unknown",
                            amountCents = b.amount,
                            // actual_cents is spend (negative); show it as positive spent, floored at 0.
                            spentCents = (-b.actualCents).coerceAtLeast(0),
                            projectedCents = pace?.projectedCents,
                            dailyAllowanceCents = pace?.dailyAllowanceCents,
                            paceStatus = pace?.status,
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
                    goal = coach?.goal,
                    net = coach?.net,
                    daysLeft = coach?.let { it.daysInMonth - it.daysElapsed },
                    uncategorizedMtdCents = coach?.uncategorizedMtdCents ?: 0,
                    loading = false,
                )
                if (coach != null) loadCoaching()
            } catch (e: Exception) {
                _state.value =
                    _state.value.copy(loading = false, error = e.message ?: "Couldn't load budgets")
            }
        }
    }

    /** Second phase: the LLM coaching prose (violet card). Never blocks the deterministic screen —
     *  the local model may be off, in which case the card simply doesn't appear. */
    private fun loadCoaching() {
        viewModelScope.launch {
            val withProse = runCatching { api.coachStatus(narrative = true) }.getOrNull() ?: return@launch
            if (withProse.narrativeSource == "llm") {
                _state.value = _state.value.copy(
                    coachHeadline = withProse.narrativeHeadline,
                    coachCoaching = withProse.narrativeCoaching,
                )
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

    // --- goal ---

    fun setGoal(amountCents: Long) {
        viewModelScope.launch {
            try {
                api.setGoal(GoalUpsert(amountCents))
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't save goal")
            }
        }
    }

    fun clearGoal() {
        viewModelScope.launch {
            try {
                api.clearGoal()
                _state.value = _state.value.copy(plan = null)
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't clear goal")
            }
        }
    }

    // --- savings plan ---

    /** "How do I get there?" — fetch the cut plan for the active goal. Computed server-side on
     *  request, never persisted; each cut is a draft applied one by one below. */
    fun loadPlan() {
        viewModelScope.launch {
            _state.value = _state.value.copy(planLoading = true, error = null)
            try {
                _state.value = _state.value.copy(plan = api.coachPlan(), planLoading = false)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    planLoading = false,
                    error = e.message ?: "Couldn't build a plan",
                )
            }
        }
    }

    fun dismissPlan() {
        _state.value = _state.value.copy(plan = null)
    }

    /** Accept one cut: PATCH the existing budget or create one at the cut amount. Optimistically
     *  drop the cut from the plan (the acceptProposal shape). */
    fun applyCut(cut: ProposedCutOut) {
        val plan = _state.value.plan
        if (plan != null) {
            _state.value = _state.value.copy(
                plan = plan.copy(cuts = plan.cuts.filterNot { it.categoryId == cut.categoryId }),
            )
        }
        viewModelScope.launch {
            try {
                if (cut.budgetId != null) {
                    api.updateBudget(cut.budgetId, BudgetUpdate(cut.toCents))
                } else {
                    api.createBudget(BudgetCreate(cut.categoryId, monthParam, cut.toCents))
                }
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't apply that cut")
                loadPlan() // restore the plan if the write didn't take
            }
        }
    }

    // --- per-category deep dive ---

    fun openCategory(categoryId: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(analysisLoading = true, error = null)
            // Deterministic figures first — the sheet renders immediately even with the LLM off.
            val quick = runCatching { api.coachCategory(categoryId, narrative = false) }.getOrNull()
            _state.value = _state.value.copy(analysis = quick, analysisLoading = false)
            if (quick == null) {
                _state.value = _state.value.copy(error = "Couldn't load that category")
                return@launch
            }
            val withProse = runCatching { api.coachCategory(categoryId, narrative = true) }.getOrNull()
            // Only upgrade if the sheet is still showing this category.
            if (withProse?.narrativeSource == "llm" &&
                _state.value.analysis?.categoryId == categoryId
            ) {
                _state.value = _state.value.copy(analysis = withProse)
            }
        }
    }

    fun dismissAnalysis() {
        _state.value = _state.value.copy(analysis = null)
    }
}
