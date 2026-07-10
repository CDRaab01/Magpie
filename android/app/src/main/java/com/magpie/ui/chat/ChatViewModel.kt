package com.magpie.ui.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.ChatMessage
import com.magpie.data.remote.ChatRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class ChatUiState(
    val messages: List<ChatMessage> = emptyList(),
    val sending: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class ChatViewModel @Inject constructor(
    private val api: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow(ChatUiState())
    val state: StateFlow<ChatUiState> = _state

    fun send(text: String) {
        val question = text.trim()
        if (question.isEmpty() || _state.value.sending) return
        // Optimistically show the user's turn; the assistant reply arrives async.
        val withUser = _state.value.messages + ChatMessage("user", question)
        _state.value = _state.value.copy(messages = withUser, sending = true, error = null)
        viewModelScope.launch {
            try {
                // Send prior turns as history; the current question rides the `message` field.
                val reply = api.chat(ChatRequest(message = question, history = _state.value.messages.dropLast(1)))
                _state.value = _state.value.copy(
                    messages = _state.value.messages + ChatMessage("assistant", reply.reply),
                    sending = false,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    sending = false,
                    error = e.message ?: "Couldn't reach Magpie",
                )
            }
        }
    }
}
