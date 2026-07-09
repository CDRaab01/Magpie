package com.magpie.ui.merchant

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.TransactionOut
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlin.math.abs

/**
 * The merchant drill-down (ROADMAP.md Wave 1 #16): every transaction at one merchant, plus the
 * roll-up the top-merchants list can't show — lifetime total, count, and average ticket. Loaded
 * on demand via the existing `q` merchant search (Tier 4 #32 plumbing), so no new endpoint.
 */
data class MerchantDetailUiState(
    val merchant: String = "",
    val transactions: List<TransactionOut> = emptyList(),
    val totalCents: Long = 0,
    val count: Int = 0,
    val averageCents: Long = 0,
    val loading: Boolean = true,
    val error: String? = null,
)

@HiltViewModel
class MerchantDetailViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow(MerchantDetailUiState())
    val state: StateFlow<MerchantDetailUiState> = _state

    private var merchant: String = ""

    /** Called once from the screen with the nav argument, and again by RefreshOnResume. */
    fun load(merchant: String) {
        this.merchant = merchant
        viewModelScope.launch {
            _state.value = _state.value.copy(merchant = merchant, error = null)
            try {
                // Only spend/refund rows count toward the merchant's spend total; an income or
                // transfer that happens to share the name shouldn't distort the average ticket.
                val txns = api.listTransactions(query = merchant)
                    .filter { it.kind == "spend" || it.kind == "refund" }
                val total = txns.sumOf { it.amount }
                val count = txns.size
                val average = if (count == 0) 0L else total / count
                _state.value = MerchantDetailUiState(
                    merchant = merchant,
                    transactions = txns,
                    totalCents = total,
                    count = count,
                    averageCents = average,
                    loading = false,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    loading = false,
                    error = e.message ?: "Couldn't load $merchant",
                )
            }
        }
    }

    /** Total magnitude for display (spend is negative; callers show it as a positive sum). */
    fun totalMagnitude(): Long = abs(_state.value.totalCents)
}
