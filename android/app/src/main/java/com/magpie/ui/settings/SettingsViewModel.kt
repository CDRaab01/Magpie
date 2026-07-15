package com.magpie.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.local.TokenStore
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.CategoryCreate
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.CategoryUpdate
import com.magpie.util.AuthEventBus
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** A fetched CSV export waiting for the screen to hand it to the share sheet (#16). */
data class ExportPayload(val filename: String, val csv: String)

data class SettingsUiState(
    val categories: List<CategoryOut> = emptyList(),
    // The signed-in SSO account, shown in the Settings header. Best-effort like the version read.
    val userName: String? = null,
    val userEmail: String? = null,
    // Shown in About; best-effort, so a failed /version read never blocks the category editor.
    val serverVersion: String? = null,
    val serverCommit: String? = null,
    val loading: Boolean = true,
    val error: String? = null,
    val exporting: Boolean = false,
    // Set when an export CSV is ready; the screen writes it to a file and launches the share sheet,
    // then clears it. Kept out of the ViewModel because the share is platform glue (Context/Intent).
    val pendingExport: ExportPayload? = null,
)

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val api: ApiService,
    private val tokenStore: TokenStore,
    private val authEventBus: AuthEventBus,
) : ViewModel() {
    private val _state = MutableStateFlow(SettingsUiState())
    val state: StateFlow<SettingsUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            // Silent refresh (see BillsViewModel): don't re-flash the spinner on RefreshOnResume.
            _state.value = _state.value.copy(error = null)
            try {
                val categories = api.listCategories()
                // Both are nice-to-have — a failed /me or /version read must not fail the screen.
                val me = runCatching { api.getMe() }.getOrNull()
                val version = runCatching { api.getVersion() }.getOrNull()
                _state.value = _state.value.copy(
                    categories = categories.sortedBy { it.name.lowercase() },
                    userName = me?.name,
                    userEmail = me?.email,
                    serverVersion = version?.version,
                    serverCommit = version?.commit,
                    loading = false,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    loading = false,
                    error = e.message ?: "Couldn't load settings",
                )
            }
        }
    }

    fun addCategory(name: String) {
        val trimmed = name.trim()
        if (trimmed.isEmpty()) return
        viewModelScope.launch {
            try {
                api.createCategory(CategoryCreate(name = trimmed))
                reload()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't add category")
            }
        }
    }

    fun renameCategory(id: String, name: String) {
        val trimmed = name.trim()
        if (trimmed.isEmpty()) return
        viewModelScope.launch {
            try {
                api.updateCategory(id, CategoryUpdate(name = trimmed))
                reload()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't rename category")
            }
        }
    }

    fun deleteCategory(id: String) {
        viewModelScope.launch {
            try {
                api.deleteCategory(id)
                reload()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't delete category")
            }
        }
    }

    /** Fetch one month's CSV (#16) and stash it as a pending share for the screen to hand off.
     *  `month` is yyyy-MM; the endpoint takes any day in the month, so we send the first. */
    fun exportMonth(month: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(exporting = true, error = null)
            try {
                val body = api.exportTransactionsCsv("$month-01")
                _state.value = _state.value.copy(
                    exporting = false,
                    pendingExport = ExportPayload(filename = "magpie-$month.csv", csv = body.string()),
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    exporting = false,
                    error = e.message ?: "Couldn't export",
                )
            }
        }
    }

    fun clearPendingExport() {
        _state.value = _state.value.copy(pendingExport = null)
    }

    /** Sign out: drop the local session and let the nav graph bounce back to sign-in — the same
     *  path a rejected refresh token takes (see TokenRefreshAuthenticator.signOut). */
    fun logout() {
        viewModelScope.launch {
            tokenStore.clear()
            authEventBus.emitLogout()
        }
    }

    /** Re-read categories after a mutation without flipping the whole screen back to a spinner. */
    private fun reload() {
        viewModelScope.launch {
            try {
                val categories = api.listCategories()
                _state.value = _state.value.copy(
                    categories = categories.sortedBy { it.name.lowercase() },
                    error = null,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Couldn't refresh categories")
            }
        }
    }
}
