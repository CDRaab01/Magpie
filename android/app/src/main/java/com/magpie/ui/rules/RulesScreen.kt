package com.magpie.ui.rules

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.ui.theme.MagpieTheme
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.PulseButton

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RulesScreen(navController: NavController) {
    val viewModel: RulesViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()

    RulesContent(
        state = state,
        onBack = { navController.popBackStack() },
        onSetEnabled = viewModel::setEnabled,
        onDelete = viewModel::delete,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun RulesContent(
    state: RulesUiState,
    onBack: () -> Unit,
    onSetEnabled: (id: String, enabled: Boolean) -> Unit,
    onDelete: (id: String) -> Unit,
) {
    var deleting by remember { mutableStateOf<RuleRow?>(null) }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Rules") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.padding(padding).fillMaxSize()) {
            state.error?.let {
                Text(
                    it,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(MagpieTheme.spacing.md),
                )
            }
            when {
                state.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    CircularProgressIndicator()
                }
                state.rules.isEmpty() -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    Text(
                        "No rules yet. Magpie adds them as it learns your recurring transactions.",
                        modifier = Modifier.padding(MagpieTheme.spacing.lg),
                    )
                }
                else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                    items(state.rules.size) { i ->
                        RuleRowCard(
                            row = state.rules[i],
                            onSetEnabled = { onSetEnabled(state.rules[i].id, it) },
                            onDelete = { deleting = state.rules[i] },
                        )
                    }
                }
            }
        }
    }

    deleting?.let { row ->
        AlertDialog(
            onDismissRequest = { deleting = null },
            title = { Text("Delete rule?") },
            text = { Text("Stop auto-filing “${row.matcher}”? Existing transactions are unchanged.") },
            confirmButton = {
                PulseButton(
                    text = "Delete",
                    compact = true,
                    onClick = {
                        onDelete(row.id)
                        deleting = null
                    },
                )
            },
            dismissButton = {
                PulseButton(
                    text = "Cancel",
                    tonal = true,
                    compact = true,
                    onClick = { deleting = null },
                )
            },
        )
    }
}

@Composable
private fun RuleRowCard(
    row: RuleRow,
    onSetEnabled: (Boolean) -> Unit,
    onDelete: () -> Unit,
) {
    val channel =
        if (row.enabled) MagpieTheme.colors.money.base else MaterialTheme.colorScheme.outline
    PanelCard(channel = channel, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(row.matcher, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    listOf(row.typeLabel, row.summary).filter { it.isNotEmpty() }.joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Switch(checked = row.enabled, onCheckedChange = onSetEnabled)
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Delete, contentDescription = "Delete rule")
            }
        }
    }
}
