package com.magpie.ui.rules

import androidx.compose.material.icons.filled.AutoAwesome
import design.pulse.ui.components.EmptyState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Remove
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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlin.math.roundToInt
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.ui.theme.MagpieTheme
import com.magpie.ui.util.RefreshOnResume
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.PulseButton

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RulesScreen(navController: NavController) {
    val viewModel: RulesViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }

    RulesContent(
        state = state,
        onBack = { navController.popBackStack() },
        onSetEnabled = viewModel::setEnabled,
        onDelete = viewModel::delete,
        onCreateSuggested = viewModel::createSuggestedRules,
        onUpdateBand = viewModel::updateBand,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun RulesContent(
    state: RulesUiState,
    onBack: () -> Unit,
    onSetEnabled: (id: String, enabled: Boolean) -> Unit,
    onDelete: (id: String) -> Unit,
    onCreateSuggested: () -> Unit = {},
    onUpdateBand: (id: String, slackDays: Int?, bandPct: Double?) -> Unit = { _, _, _ -> },
) {
    var deleting by remember { mutableStateOf<RuleRow?>(null) }
    var editing by remember { mutableStateOf<RuleRow?>(null) }
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
            if (!state.loading && state.suggestedRuleCount > 0) {
                SuggestRulesBanner(
                    count = state.suggestedRuleCount,
                    creating = state.creatingRules,
                    onCreate = onCreateSuggested,
                )
            }
            when {
                state.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    CircularProgressIndicator()
                }
                state.rules.isEmpty() -> EmptyState(
                    icon = Icons.Default.AutoAwesome,
                    title = "No rules yet",
                    subtitle = "Magpie adds them as it learns your recurring transactions.",
                )
                else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                    items(state.rules.size) { i ->
                        RuleRowCard(
                            row = state.rules[i],
                            onSetEnabled = { onSetEnabled(state.rules[i].id, it) },
                            onDelete = { deleting = state.rules[i] },
                            onEdit = { editing = state.rules[i] },
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

    editing?.let { row ->
        var slack by remember(row.id) { mutableIntStateOf(row.slackDays ?: 0) }
        var bandPctInt by remember(row.id) { mutableIntStateOf(((row.bandPct ?: 0.0) * 100).roundToInt()) }
        AlertDialog(
            onDismissRequest = { editing = null },
            title = { Text("Tune “${row.matcher}”") },
            text = {
                Column {
                    if (row.cadenceKind != null) {
                        StepperRow(
                            label = "Timing tolerance",
                            value = "±$slack d",
                            onMinus = { if (slack > 0) slack-- },
                            onPlus = { slack++ },
                        )
                        Spacer(Modifier.height(4.dp))
                    }
                    if (row.bandPct != null) {
                        StepperRow(
                            label = "Amount tolerance",
                            value = "±$bandPctInt%",
                            onMinus = { if (bandPctInt >= 5) bandPctInt -= 5 },
                            onPlus = { bandPctInt += 5 },
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "A wider band auto-files more variation; a tighter one sends borderline hits to review.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            },
            confirmButton = {
                PulseButton(
                    text = "Save",
                    compact = true,
                    onClick = {
                        onUpdateBand(
                            row.id,
                            if (row.cadenceKind != null) slack else null,
                            if (row.bandPct != null) bandPctInt / 100.0 else null,
                        )
                        editing = null
                    },
                )
            },
            dismissButton = {
                PulseButton(text = "Cancel", tonal = true, compact = true, onClick = { editing = null })
            },
        )
    }
}

/** A label + a −/value/+ stepper, for the inline band editor. */
@Composable
private fun StepperRow(label: String, value: String, onMinus: () -> Unit, onPlus: () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        IconButton(onClick = onMinus) { Icon(Icons.Default.Remove, contentDescription = "Decrease") }
        Text(value, style = MaterialTheme.typography.titleSmall, color = MagpieTheme.colors.money.base)
        IconButton(onClick = onPlus) { Icon(Icons.Default.Add, contentDescription = "Increase") }
    }
}

/**
 * The "turn your categorized history into rules" banner (#25). When merchants the owner has
 * already categorized could become auto-filing rules, this offers to create them in one tap —
 * the phone-side of `POST /rules/from-confirmed`. Money channel (this is teal-primary automation,
 * not an AI draft), with a spinner while the create call is in flight.
 */
@Composable
private fun SuggestRulesBanner(count: Int, creating: Boolean, onCreate: () -> Unit) {
    val channel = MagpieTheme.colors.money.base
    PanelCard(
        channel = channel,
        modifier = Modifier.fillMaxWidth().padding(MagpieTheme.spacing.md),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    "Auto-file $count more merchant${if (count == 1) "" else "s"}",
                    style = MaterialTheme.typography.titleSmall,
                    color = channel,
                )
                Text(
                    "You've categorized these — make rules so they file themselves next time.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (creating) {
                CircularProgressIndicator(modifier = Modifier.padding(start = 12.dp))
            } else {
                PulseButton(text = "Create", compact = true, onClick = onCreate)
            }
        }
    }
}

@Composable
private fun RuleRowCard(
    row: RuleRow,
    onSetEnabled: (Boolean) -> Unit,
    onDelete: () -> Unit,
    onEdit: () -> Unit = {},
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
            if (row.bandEditable) {
                IconButton(onClick = onEdit) {
                    Icon(Icons.Default.Edit, contentDescription = "Tune rule band")
                }
            }
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Delete, contentDescription = "Delete rule")
            }
        }
    }
}
