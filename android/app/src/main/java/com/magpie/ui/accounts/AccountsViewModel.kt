package com.magpie.ui.accounts

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.local.SnapshotStore
import com.magpie.data.remote.AccountCreate
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.CheckpointCreate
import com.magpie.data.remote.ImportSummaryOut
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
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

data class AccountsUiState(
    val accounts: List<AccountOut> = emptyList(),
    val loading: Boolean = true,
    val importing: Boolean = false,
    val importResult: ImportSummaryOut? = null,
    val error: String? = null,
    // Non-null when the list was restored from the offline snapshot rather than the server: the
    // epoch-ms it was captured, for the stale banner. While set, every mutation (add/import/
    // checkpoint/delete) is inert — writes need the server.
    val staleAsOfMs: Long? = null,
)

/** The serializable slice of [AccountsUiState] cached for offline. */
@Serializable
private data class AccountsSnapshot(
    val accounts: List<AccountOut>,
    // When the snapshot was written, so an offline open can show "as of <time>".
    val cachedAtMs: Long = 0L,
)

@HiltViewModel
class AccountsViewModel @Inject constructor(
    private val api: ApiService,
    private val snapshots: SnapshotStore,
) : ViewModel() {
    private val _state = MutableStateFlow(AccountsUiState())
    val state: StateFlow<AccountsUiState> = _state
    private val json = Json { ignoreUnknownKeys = true }

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            // Silent refresh (see BillsViewModel): don't re-flash the spinner on RefreshOnResume.
            _state.value = _state.value.copy(error = null)
            try {
                val accounts = api.listAccounts()
                _state.value = _state.value.copy(accounts = accounts, loading = false, staleAsOfMs = null)
                // Cache the raw list so a later offline open shows last-known, not an error.
                runCatching {
                    snapshots.save(
                        SnapshotStore.ACCOUNTS,
                        json.encodeToString(
                            AccountsSnapshot(accounts, cachedAtMs = System.currentTimeMillis()),
                        ),
                    )
                }
            } catch (e: IOException) {
                // Server unreachable (a network failure, not a rejection): fall back to the
                // last-known accounts read-only instead of erroring.
                val cached = snapshots.read(SnapshotStore.ACCOUNTS)
                    ?.let { runCatching { json.decodeFromString<AccountsSnapshot>(it) }.getOrNull() }
                _state.value = if (cached != null) {
                    _state.value.copy(
                        accounts = cached.accounts,
                        loading = false,
                        staleAsOfMs = cached.cachedAtMs.takeIf { it > 0L },
                    )
                } else {
                    _state.value.copy(loading = false, error = e.message ?: "Couldn't load accounts")
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Couldn't load accounts")
            }
        }
    }

    /** Offline-stale screen is read-only — the screen disables the actions; this is the backstop. */
    private fun isStale(): Boolean = _state.value.staleAsOfMs != null

    fun importCsv(accountId: String, institution: String, fileBytes: ByteArray, fileName: String) {
        if (isStale()) return
        viewModelScope.launch {
            _state.value = _state.value.copy(importing = true, error = null, importResult = null)
            try {
                val textPlain = "text/plain".toMediaTypeOrNull()
                val accountIdBody = accountId.toRequestBody(textPlain)
                val institutionBody = institution.toRequestBody(textPlain)
                val filePart = MultipartBody.Part.createFormData(
                    "file", fileName, fileBytes.toRequestBody("text/csv".toMediaTypeOrNull()),
                )
                val result = api.importCsv(accountIdBody, institutionBody, filePart)
                _state.value = _state.value.copy(importing = false, importResult = result)
                load() // refresh balances now that new transactions may exist
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    importing = false,
                    error = e.message ?: "Import failed",
                )
            }
        }
    }

    fun createAccount(name: String, institution: String, type: String, last4: String?) {
        if (isStale()) return
        viewModelScope.launch {
            _state.value = _state.value.copy(error = null)
            try {
                api.createAccount(
                    AccountCreate(name = name, institution = institution, type = type, last4 = last4),
                )
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't add account")
            }
        }
    }

    fun addCheckpoint(accountId: String, statementDate: String, statedBalanceCents: Long) {
        if (isStale()) return
        viewModelScope.launch {
            _state.value = _state.value.copy(error = null)
            try {
                api.addCheckpoint(
                    accountId,
                    CheckpointCreate(statementDate = statementDate, statedBalanceCents = statedBalanceCents),
                )
                load() // the delta/honesty meter and anchored balance change once a checkpoint lands
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't save balance")
            }
        }
    }

    fun deleteAccount(accountId: String) {
        if (isStale()) return
        viewModelScope.launch {
            _state.value = _state.value.copy(error = null)
            try {
                api.deleteAccount(accountId)
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't delete account")
            }
        }
    }

    fun dismissImportResult() {
        _state.value = _state.value.copy(importResult = null)
    }
}
