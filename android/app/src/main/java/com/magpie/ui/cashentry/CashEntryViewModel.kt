package com.magpie.ui.cashentry

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.CategoryOut
import com.magpie.data.repository.TransactionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class CashEntryFormState(
    val accounts: List<AccountOut> = emptyList(),
    val categories: List<CategoryOut> = emptyList(),
    val saving: Boolean = false,
    val saved: Boolean = false,
    val error: String? = null,
)

/** "spend" | "income" | "refund" — transfers aren't manually creatable (they're a matched pair,
 * the rules engine's job, CLAUDE.md Phase 5+), so the entry form only offers everyday kinds. */
val CASH_ENTRY_KINDS = listOf("spend", "income", "refund")

@HiltViewModel
class CashEntryViewModel @Inject constructor(
    private val api: ApiService,
    private val transactionRepository: TransactionRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(CashEntryFormState())
    val state: StateFlow<CashEntryFormState> = _state

    init {
        viewModelScope.launch {
            try {
                val accounts = api.listAccounts()
                val categories = api.listCategories()
                _state.value = _state.value.copy(accounts = accounts, categories = categories)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't load accounts")
            }
        }
    }

    /** [dollars] is always entered as a positive amount; the sign convention (CLAUDE.md §2:
     * spend negative, income/refund positive) is applied here, not left to the user to get right. */
    fun submit(
        accountId: String,
        dollars: Double,
        kind: String,
        merchant: String?,
        categoryId: String?,
    ) {
        viewModelScope.launch {
            _state.value = _state.value.copy(saving = true, error = null)
            val cents = Math.round(dollars * 100)
            val signedCents = if (kind == "spend") -cents else cents
            try {
                transactionRepository.addCashEntry(
                    accountId = accountId,
                    amountCents = signedCents,
                    currency = "USD",
                    date = LocalDate.now().toString(),
                    kind = kind,
                    merchantRaw = merchant?.takeIf { it.isNotBlank() },
                    categoryId = categoryId,
                )
                _state.value = _state.value.copy(saving = false, saved = true)
            } catch (e: Exception) {
                _state.value = _state.value.copy(saving = false, error = e.message ?: "Couldn't save")
            }
        }
    }
}
