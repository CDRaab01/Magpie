package com.magpie.ui.bills

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.local.SnapshotStore
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.BillOut
import dagger.hilt.android.lifecycle.HiltViewModel
import java.io.IOException
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

data class BillsUiState(
    val bills: List<BillOut> = emptyList(),
    val loading: Boolean = true,
    val error: String? = null,
    // Non-null when the list was restored from the offline snapshot rather than the server: the
    // epoch-ms it was captured, for the stale banner. (Bills is read-only, so nothing to disable.)
    val staleAsOfMs: Long? = null,
)

/** The serializable slice of [BillsUiState] cached for offline. */
@Serializable
private data class BillsSnapshot(
    val bills: List<BillOut>,
    // When the snapshot was written, so an offline open can show "as of <time>".
    val cachedAtMs: Long = 0L,
)

@HiltViewModel
class BillsViewModel @Inject constructor(
    private val api: ApiService,
    private val snapshots: SnapshotStore,
) : ViewModel() {
    private val _state = MutableStateFlow(BillsUiState())
    val state: StateFlow<BillsUiState> = _state
    private val json = Json { ignoreUnknownKeys = true }

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            // Silent refresh: keep `loading` as-is (true only on the first load, from the initial
            // state) so RefreshOnResume doesn't flash the spinner over already-loaded content.
            _state.value = _state.value.copy(error = null)
            try {
                val bills = api.listBills()
                _state.value = _state.value.copy(bills = bills, loading = false, staleAsOfMs = null)
                // Cache the raw list so a later offline open shows last-known, not an error.
                runCatching {
                    snapshots.save(
                        SnapshotStore.BILLS,
                        json.encodeToString(BillsSnapshot(bills, cachedAtMs = System.currentTimeMillis())),
                    )
                }
            } catch (e: IOException) {
                // Server unreachable (a network failure, not a rejection): fall back to the
                // last-known bills instead of erroring.
                val cached = snapshots.read(SnapshotStore.BILLS)
                    ?.let { runCatching { json.decodeFromString<BillsSnapshot>(it) }.getOrNull() }
                _state.value = if (cached != null) {
                    _state.value.copy(
                        bills = cached.bills,
                        loading = false,
                        staleAsOfMs = cached.cachedAtMs.takeIf { it > 0L },
                    )
                } else {
                    _state.value.copy(loading = false, error = e.message ?: "Couldn't load bills")
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Couldn't load bills")
            }
        }
    }
}
