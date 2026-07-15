package com.magpie.ui.rules

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.RuleAmountBand
import com.magpie.data.remote.RuleCadence
import com.magpie.data.remote.RuleOut
import com.magpie.data.remote.RuleUpdate
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** A rule flattened for display — matcher headline + a one-line "why it fires" summary. */
data class RuleRow(
    val id: String,
    val typeLabel: String,
    val matcher: String,
    val summary: String,
    val enabled: Boolean,
    // Raw editable values (for the inline band editor); null when the rule type has no band/cadence.
    val cadenceKind: String? = null,
    val slackDays: Int? = null,
    val bandPct: Double? = null,
) {
    /** Recurring income/bill rules carry a tolerance band + cadence the owner can tune inline. */
    val bandEditable: Boolean get() = cadenceKind != null || bandPct != null
}

data class RulesUiState(
    val rules: List<RuleRow> = emptyList(),
    val loading: Boolean = true,
    val error: String? = null,
    // How many merchants you've categorized could become auto-filing rules right now (#25) — a
    // best-effort dry-run preview. Zero (or null while unknown) hides the "create rules" banner.
    val suggestedRuleCount: Int = 0,
    // True while a create-rules call is in flight, so the banner shows progress and can't double-fire.
    val creatingRules: Boolean = false,
)

private fun typeLabel(type: String): String = when (type) {
    "recurring_income" -> "Income"
    "recurring_bill" -> "Bill"
    "transfer_match" -> "Transfer"
    "merchant_category" -> "Category rule"
    else -> type
}

private fun summarize(rule: RuleOut, categoryName: String?): String {
    val parts = mutableListOf<String>()
    rule.cadence?.kind?.let { kind ->
        val slack = rule.cadence.slackDays
        parts += if (slack != null) "$kind ±${slack}d" else kind
    }
    rule.amountBand?.pct?.let { pct -> parts += "±${(pct * 100).toInt()}%" }
    categoryName?.let { parts += "→ $it" }
    return parts.joinToString(" · ")
}

@HiltViewModel
class RulesViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow(RulesUiState())
    val state: StateFlow<RulesUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            // Silent refresh (see BillsViewModel): don't re-flash the spinner on RefreshOnResume.
            _state.value = _state.value.copy(error = null)
            try {
                val rules = api.listRules()
                val nameById = api.listCategories().associate { it.id to it.name }
                val rows = rules
                    .sortedBy { it.type }
                    .map { r ->
                        RuleRow(
                            id = r.id,
                            typeLabel = typeLabel(r.type),
                            matcher = r.matcher,
                            summary = summarize(r, r.categoryId?.let { nameById[it] }),
                            enabled = r.enabled,
                            cadenceKind = r.cadence?.kind,
                            slackDays = r.cadence?.slackDays,
                            bandPct = r.amountBand?.pct,
                        )
                    }
                _state.value = _state.value.copy(rules = rows, loading = false)
                // Best-effort dry-run preview of how many rules could be created from merchants the
                // owner has already categorized — surfaces the "create rules" banner. A hiccup just
                // leaves the count at 0 (banner hidden); it never blocks the list from rendering.
                val suggested =
                    runCatching { api.promoteConfirmedRules(dryRun = true).rulesCreated }
                        .getOrDefault(0)
                _state.value = _state.value.copy(suggestedRuleCount = suggested)
            } catch (e: Exception) {
                _state.value =
                    _state.value.copy(loading = false, error = e.message ?: "Couldn't load rules")
            }
        }
    }

    /** Promote every eligible confirmed merchant into a rule (the banner's action, #25). */
    fun createSuggestedRules() {
        if (_state.value.creatingRules) return
        _state.value = _state.value.copy(creatingRules = true, error = null)
        viewModelScope.launch {
            try {
                api.promoteConfirmedRules(dryRun = false)
                _state.value = _state.value.copy(creatingRules = false, suggestedRuleCount = 0)
                load() // pull in the freshly created rules
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    creatingRules = false,
                    error = e.message ?: "Couldn't create rules",
                )
            }
        }
    }

    fun setEnabled(id: String, enabled: Boolean) {
        // Optimistic — the switch responds instantly; revert by reloading if the server rejects it.
        _state.value = _state.value.copy(
            rules = _state.value.rules.map { if (it.id == id) it.copy(enabled = enabled) else it },
        )
        viewModelScope.launch {
            try {
                api.updateRule(id, RuleUpdate(enabled))
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't update rule")
                load()
            }
        }
    }

    /** Save an inline band edit: the recurring rule's cadence slack (± days) and amount tolerance (± %). */
    fun updateBand(id: String, slackDays: Int?, bandPct: Double?) {
        val row = _state.value.rules.find { it.id == id } ?: return
        val cadence = row.cadenceKind?.let { RuleCadence(kind = it, slackDays = slackDays) }
        val band = bandPct?.let { RuleAmountBand(pct = it) }
        viewModelScope.launch {
            try {
                api.updateRule(id, RuleUpdate(cadence = cadence, amountBand = band))
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't update rule")
            }
        }
    }

    fun delete(id: String) {
        viewModelScope.launch {
            try {
                api.deleteRule(id)
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't delete rule")
            }
        }
    }
}
