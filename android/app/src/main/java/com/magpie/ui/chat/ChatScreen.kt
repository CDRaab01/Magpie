package com.magpie.ui.chat

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.ChatMessage
import com.magpie.ui.theme.MagpieTheme
import design.pulse.ui.components.PanelCard

/** Thin ViewModel-wired wrapper. [ChatContent] below is the pure, screenshot-testable half. */
@Composable
fun ChatScreen(navController: NavController) {
    val viewModel: ChatViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    ChatContent(state = state, onBack = { navController.popBackStack() }, onSend = viewModel::send)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ChatContent(
    state: ChatUiState,
    onBack: () -> Unit,
    onSend: (String) -> Unit,
) {
    var draft by remember { mutableStateOf("") }
    val listState = rememberLazyListState()
    LaunchedEffect(state.messages.size) {
        if (state.messages.isNotEmpty()) listState.animateScrollToItem(state.messages.size - 1)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Ask Magpie") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
        bottomBar = {
            Row(
                modifier = Modifier.fillMaxWidth().padding(MagpieTheme.spacing.sm),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextField(
                    value = draft,
                    onValueChange = { draft = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("How much on dining vs May?") },
                    maxLines = 3,
                )
                IconButton(
                    enabled = draft.isNotBlank() && !state.sending,
                    onClick = { onSend(draft); draft = "" },
                ) {
                    if (state.sending) {
                        CircularProgressIndicator(Modifier.padding(4.dp))
                    } else {
                        Icon(Icons.Default.Send, contentDescription = "Send")
                    }
                }
            }
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            state.error?.let {
                Text(it, color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(MagpieTheme.spacing.md))
            }
            if (state.messages.isEmpty()) {
                Box(Modifier.fillMaxSize(), Alignment.Center) {
                    Text(
                        "Ask about your spending — Magpie answers from your\nnumbers only, and never gives advice.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize().padding(MagpieTheme.spacing.md),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(state.messages) { msg -> MessageBubble(msg) }
                }
            }
        }
    }
}

/** User turns lean right in the money channel; the assistant's answers lean left in the AI violet
 *  voice — the same "the model said this" cue the insight card uses. */
@Composable
private fun MessageBubble(msg: ChatMessage) {
    val isUser = msg.role == "user"
    val channel = if (isUser) MagpieTheme.colors.money.base else MagpieTheme.colors.aiVoice.base
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Box(modifier = Modifier.widthIn(max = 300.dp).clip(MaterialTheme.shapes.medium)) {
            PanelCard(channel = channel) {
                Text(msg.content, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}
