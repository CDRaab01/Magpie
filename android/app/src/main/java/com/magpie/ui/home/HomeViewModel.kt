package com.magpie.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.local.SnapshotStore
import com.magpie.data.remote.AccountCreate
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.MonthSummaryOut
import com.magpie.data.remote.MonthlyInsightOut
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.data.remote.UpcomingBillOut
import com.magpie.widget.WidgetRefresher
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import java.time.LocalTime
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

private fun greetingForNow(): String = when (LocalTime.now().hour) {
    in 5..11 -> "Good morning"
    in 12..16 -> "Good afternoon"
    else -> "Good evening"
}

sealed interface HomeUiState {
    object Loading : HomeUiState
    /** No accounts yet — nothing can be logged until one exists. */
    object NeedsAccount : HomeUiState
    data class Ready(
        val summary: MonthlySummaryOut,
        val accounts: List<AccountOut>,
        // For the hero (#28): the greeting is resolved here (not in the composable) so the pure
        // Content stays deterministic for screenshot tests; plus how many rows await review and the
        // soonest upcoming bill for the status line.
        val greeting: String = "Hello",
        val reviewCount: Int = 0,
        val nextBill: UpcomingBillOut? = null,
        // The genre's headline number (#12a): depository balances minus bills due before the next
        // paycheck. Best-effort — null if the endpoint hiccups, so the hero degrades to just the
        // status line rather than blanking.
        val safeToSpendCents: Long? = null,
        // 6-month income/spend/net series for the month-tile sparklines (#13). Best-effort; empty
        // just means the tiles render without their trend line (the value still shows).
        val history: List<MonthSummaryOut> = emptyList(),
        // The month's "what changed" insight (#18). Fetched deterministic-only (no LLM) so Home
        // never waits on a model call; null on any hiccup, and the card hides itself when there's
        // nothing notable to say.
        val insight: MonthlyInsightOut? = null,
        // Non-null when this panel was restored from the offline snapshot rather than the server:
        // the epoch-ms it was captured, for the subtle "as of <time>" stale indicator.
        val asOfMs: Long? = null,
    ) : HomeUiState
    data class Error(val message: String) : HomeUiState
}

/** The serializable slice of [HomeUiState.Ready] cached for offline (the greeting is recomputed). */
@Serializable
private data class HomeSnapshot(
    val summary: MonthlySummaryOut,
    val accounts: List<AccountOut>,
    val reviewCount: Int,
    val nextBill: UpcomingBillOut?,
    val safeToSpendCents: Long?,
    val history: List<MonthSummaryOut>,
    val insight: MonthlyInsightOut?,
    // When the snapshot was written, so an offline open can show "as of <time>".
    val cachedAtMs: Long = 0L,
)

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val api: ApiService,
    private val snapshots: SnapshotStore,
    private val widgetRefresher: WidgetRefresher,
) : ViewModel() {
    private val _state = MutableStateFlow<HomeUiState>(HomeUiState.Loading)
    val state: StateFlow<HomeUiState> = _state
    private val json = Json { ignoreUnknownKeys = true }

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            // Silent refresh: don't flash the spinner on resume-refresh. The initial StateFlow value
            // is already Loading, so the first load shows the spinner; later loads (RefreshOnResume,
            // post-create) keep the current content on screen and swap in fresh data when it arrives.
            try {
                val accounts = api.listAccounts()
                if (accounts.isEmpty()) {
                    _state.value = HomeUiState.NeedsAccount
                    return@launch
                }
                val now = LocalDate.now()
                val summary = api.monthlySummary(now.year, now.monthValue)
                // Best-effort status inputs for the hero — a hiccup here shouldn't blank the panel.
                val reviewCount =
                    runCatching { api.listTransactions(reviewState = "needs_review").size }
                        .getOrDefault(0)
                val nextBill =
                    runCatching { api.getCashflow().bills.firstOrNull() }.getOrNull()
                val safeToSpend =
                    runCatching { api.getSafeToSpend().safeToSpendCents }.getOrNull()
                val history =
                    runCatching { api.getHistory(6).months }.getOrDefault(emptyList())
                val insight =
                    runCatching {
                        api.getMonthlyInsight(month = "%04d-%02d-01".format(now.year, now.monthValue))
                    }.getOrNull()
                _state.value = HomeUiState.Ready(
                    summary, accounts, greetingForNow(), reviewCount, nextBill, safeToSpend,
                    history, insight,
                )
                // Cache this assembled view so a later offline open shows last-known, not an error.
                runCatching {
                    snapshots.save(
                        SnapshotStore.HOME,
                        json.encodeToString(
                            HomeSnapshot(
                                summary, accounts, reviewCount, nextBill, safeToSpend, history,
                                insight, cachedAtMs = System.currentTimeMillis(),
                            ),
                        ),
                    )
                    // Push the fresh snapshot to the home-screen widget so it updates now, not on
                    // Android's next periodic tick.
                    widgetRefresher.refresh()
                }
            } catch (e: Exception) {
                // Offline / server unreachable: fall back to the last-known Home instead of erroring.
                val cached = snapshots.read(SnapshotStore.HOME)
                    ?.let { runCatching { json.decodeFromString<HomeSnapshot>(it) }.getOrNull() }
                _state.value = if (cached != null) {
                    HomeUiState.Ready(
                        cached.summary, cached.accounts, greetingForNow(), cached.reviewCount,
                        cached.nextBill, cached.safeToSpendCents, cached.history, cached.insight,
                        asOfMs = cached.cachedAtMs.takeIf { it > 0L },
                    )
                } else {
                    HomeUiState.Error(e.message ?: "Couldn't reach Magpie")
                }
            }
        }
    }

    fun createFirstAccount(name: String, institution: String, type: String, last4: String?) {
        viewModelScope.launch {
            try {
                api.createAccount(
                    AccountCreate(name = name, institution = institution, type = type, last4 = last4),
                )
                load()
            } catch (e: Exception) {
                _state.value = HomeUiState.Error(e.message ?: "Couldn't create the account")
            }
        }
    }
}
