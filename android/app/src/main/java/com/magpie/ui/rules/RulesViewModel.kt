package com.magpie.ui.rules

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
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
)

data class RulesUiState(
    val rules: List<RuleRow> = emptyList(),
    val loading: Boolean = true,
    val error: String? = null,
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
            _state.value = _state.value.copy(loading = true, error = null)
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
                        )
                    }
                _state.value = _state.value.copy(rules = rows, loading = false)
            } catch (e: Exception) {
                _state.value =
                    _state.value.copy(loading = false, error = e.message ?: "Couldn't load rules")
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
