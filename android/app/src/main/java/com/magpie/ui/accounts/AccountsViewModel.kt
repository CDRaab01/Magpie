package com.magpie.ui.accounts

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.AccountCreate
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.ImportSummaryOut
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

data class AccountsUiState(
    val accounts: List<AccountOut> = emptyList(),
    val loading: Boolean = true,
    val importing: Boolean = false,
    val importResult: ImportSummaryOut? = null,
    val error: String? = null,
)

@HiltViewModel
class AccountsViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow(AccountsUiState())
    val state: StateFlow<AccountsUiState> = _state

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                _state.value = _state.value.copy(accounts = api.listAccounts(), loading = false)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Couldn't load accounts")
            }
        }
    }

    fun importCsv(accountId: String, institution: String, fileBytes: ByteArray, fileName: String) {
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

    fun deleteAccount(accountId: String) {
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
