package com.magpie.ui.transactions

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.SplitPart
import com.magpie.data.remote.SplitRequest
import com.magpie.data.remote.TransactionOut
import com.magpie.data.remote.TransactionUpdate
import com.magpie.data.repository.TransactionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/**
 * Transactions filter chips (#32) — now server-backed so they stay correct under offset
 * pagination (a client-side filter would only see the loaded pages). [serverReviewState]/
 * [serverKind] translate to the `/transactions` query params.
 */
enum class TxnFilter(val label: String, val serverReviewState: String?, val serverKind: String?) {
    ALL("All", null, null),
    NEEDS_REVIEW("Needs review", "needs_review", null),
    SPEND("Spend", null, "spend"),
    INCOME("Income", null, "income"),
}

sealed interface TransactionsUiState {
    object Loading : TransactionsUiState
    data class Ready(
        val items: List<TransactionOut>,
        val categoryNamesById: Map<String, String>,
        val accounts: List<AccountOut>,
        val categories: List<CategoryOut>,
        val filter: TxnFilter,
        val accountId: String?,
        val query: String,
        val appending: Boolean = false,
        val endReached: Boolean = false,
        // Non-null when these rows came from the offline read-mirror rather than the server: the
        // epoch-ms the cache was captured, for the subtle "as of <time>" stale indicator.
        val staleAsOfMs: Long? = null,
    ) : TransactionsUiState
    data class Error(val message: String) : TransactionsUiState
}

@HiltViewModel
class TransactionsViewModel @Inject constructor(
    private val transactionRepository: TransactionRepository,
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow<TransactionsUiState>(TransactionsUiState.Loading)
    val state: StateFlow<TransactionsUiState> = _state

    // Current query criteria, held outside the UI state so load()/paging read a single source.
    private var filter = TxnFilter.ALL
    private var accountId: String? = null
    private var query: String = ""
    private var searchJob: Job? = null

    init {
        load()
    }

    /** Refresh from the top (RefreshOnResume + first load). Silent: keeps current rows on screen. */
    fun load() {
        viewModelScope.launch {
            try {
                val accounts = runCatching { api.listAccounts() }.getOrDefault(emptyList())
                val categories = runCatching { api.listCategories() }.getOrDefault(emptyList())
                // The default view opens through the offline read-mirror; a filtered/searched view
                // stays online-only (nothing sensible to cache per filter+offset combination).
                val page: List<TransactionOut>
                val staleAsOfMs: Long?
                if (isDefaultView()) {
                    val cached = transactionRepository.defaultFirstPage(PAGE_SIZE)
                    page = cached.items
                    staleAsOfMs = cached.staleAsOfMs
                } else {
                    page = fetchPage(offset = 0)
                    staleAsOfMs = null
                }
                _state.value = TransactionsUiState.Ready(
                    items = page,
                    categoryNamesById = categories.associate { it.id to it.name },
                    accounts = accounts,
                    categories = categories,
                    filter = filter,
                    accountId = accountId,
                    query = query,
                    // Offline (stale) rows can't paginate — there is only the one cached page.
                    endReached = staleAsOfMs != null || page.size < PAGE_SIZE,
                    staleAsOfMs = staleAsOfMs,
                )
            } catch (e: Exception) {
                if (_state.value !is TransactionsUiState.Ready) {
                    _state.value = TransactionsUiState.Error(e.message ?: "Couldn't load transactions")
                }
            }
        }
    }

    /** The unfiltered, unsearched, all-accounts view — the only one backed by the offline mirror. */
    private fun isDefaultView(): Boolean =
        filter == TxnFilter.ALL && accountId == null && query.isBlank()

    private suspend fun fetchPage(offset: Int): List<TransactionOut> =
        transactionRepository.listTransactionsPage(
            reviewState = filter.serverReviewState,
            kind = filter.serverKind,
            accountId = accountId,
            query = query,
            limit = PAGE_SIZE,
            offset = offset,
        )

    /** Re-query from offset 0 after a filter/search change, keeping the shell (accounts/categories). */
    private fun requery() {
        val cur = _state.value as? TransactionsUiState.Ready ?: return _state.let { load() }
        _state.value = cur.copy(filter = filter, accountId = accountId, query = query)
        viewModelScope.launch {
            try {
                // A requery is a fresh online fetch (filter/search/account changed), so any prior
                // stale marker is cleared.
                val page: List<TransactionOut>
                val staleAsOfMs: Long?
                if (isDefaultView()) {
                    val cached = transactionRepository.defaultFirstPage(PAGE_SIZE)
                    page = cached.items
                    staleAsOfMs = cached.staleAsOfMs
                } else {
                    page = fetchPage(offset = 0)
                    staleAsOfMs = null
                }
                _state.value = (_state.value as? TransactionsUiState.Ready ?: cur).copy(
                    items = page,
                    appending = false,
                    endReached = staleAsOfMs != null || page.size < PAGE_SIZE,
                    staleAsOfMs = staleAsOfMs,
                )
            } catch (e: Exception) {
                _state.value = TransactionsUiState.Error(e.message ?: "Couldn't load transactions")
            }
        }
    }

    fun setFilter(f: TxnFilter) {
        if (f == filter) return
        filter = f
        requery()
    }

    fun setAccount(id: String?) {
        if (id == accountId) return
        accountId = id
        requery()
    }

    /** Debounced so a search box keystroke doesn't fire a request per character. */
    fun setQuery(q: String) {
        query = q
        (_state.value as? TransactionsUiState.Ready)?.let { _state.value = it.copy(query = q) }
        searchJob?.cancel()
        searchJob = viewModelScope.launch {
            delay(300)
            requery()
        }
    }

    /** Infinite scroll: append the next page when the list nears its end. */
    fun loadMore() {
        val cur = _state.value as? TransactionsUiState.Ready ?: return
        if (cur.appending || cur.endReached) return
        _state.value = cur.copy(appending = true)
        viewModelScope.launch {
            try {
                val next = fetchPage(offset = cur.items.size)
                val merged = cur.items + next.filter { n -> cur.items.none { it.id == n.id } }
                _state.value = (_state.value as? TransactionsUiState.Ready ?: cur).copy(
                    items = merged,
                    appending = false,
                    endReached = next.size < PAGE_SIZE,
                )
            } catch (e: Exception) {
                (_state.value as? TransactionsUiState.Ready)?.let { _state.value = it.copy(appending = false) }
            }
        }
    }

    /** #26: recategorize a row (and mark it confirmed — accepting the correction). */
    fun recategorize(transactionId: String, categoryId: String) {
        viewModelScope.launch {
            try {
                api.updateTransaction(
                    transactionId,
                    TransactionUpdate(categoryId = categoryId, reviewState = "confirmed"),
                )
                patchRow(transactionId) { it.copy(categoryId = categoryId, reviewState = "confirmed") }
            } catch (e: Exception) {
                _state.value = TransactionsUiState.Error(e.message ?: "Couldn't recategorize")
                load()
            }
        }
    }

    /** #26: delete a manual entry. */
    fun delete(transactionId: String) {
        viewModelScope.launch {
            try {
                transactionRepository.deleteTransaction(transactionId)
                (_state.value as? TransactionsUiState.Ready)?.let { cur ->
                    _state.value = cur.copy(items = cur.items.filterNot { it.id == transactionId })
                }
            } catch (e: Exception) {
                _state.value = TransactionsUiState.Error(e.message ?: "Couldn't delete")
                load()
            }
        }
    }

    fun split(transactionId: String, parts: List<SplitPart>) {
        viewModelScope.launch {
            try {
                api.splitTransaction(transactionId, SplitRequest(parts))
            } catch (e: Exception) {
                _state.value = TransactionsUiState.Error(e.message ?: "Couldn't split")
            }
            load()
        }
    }

    private fun patchRow(id: String, transform: (TransactionOut) -> TransactionOut) {
        (_state.value as? TransactionsUiState.Ready)?.let { cur ->
            _state.value = cur.copy(items = cur.items.map { if (it.id == id) transform(it) else it })
        }
    }

    private companion object {
        const val PAGE_SIZE = 50
    }
}
