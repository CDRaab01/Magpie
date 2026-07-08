package com.magpie.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.CategoryCreate
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.CategoryUpdate
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class SettingsUiState(
    val categories: List<CategoryOut> = emptyList(),
    // Shown in About; best-effort, so a failed /version read never blocks the category editor.
    val serverVersion: String? = null,
    val serverCommit: String? = null,
    val loading: Boolean = true,
    val error: String? = null,
)

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow(SettingsUiState())
    val state: StateFlow<SettingsUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val categories = api.listCategories()
                // About is nice-to-have — don't let a version fetch failure fail the screen.
                val version = runCatching { api.getVersion() }.getOrNull()
                _state.value = _state.value.copy(
                    categories = categories.sortedBy { it.name.lowercase() },
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
