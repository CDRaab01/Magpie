package com.magpie.ui.bills

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.BillOut
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class BillsUiState(
    val bills: List<BillOut> = emptyList(),
    val loading: Boolean = true,
    val error: String? = null,
)

@HiltViewModel
class BillsViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow(BillsUiState())
    val state: StateFlow<BillsUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            // Silent refresh: keep `loading` as-is (true only on the first load, from the initial
            // state) so RefreshOnResume doesn't flash the spinner over already-loaded content.
            _state.value = _state.value.copy(error = null)
            try {
                _state.value = _state.value.copy(bills = api.listBills(), loading = false)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Couldn't load bills")
            }
        }
    }
}
