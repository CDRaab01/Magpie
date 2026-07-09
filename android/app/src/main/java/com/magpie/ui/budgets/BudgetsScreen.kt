package com.magpie.ui.budgets

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.text.KeyboardOptions
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.CategoryOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.PulseButton

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BudgetsScreen(navController: NavController) {
    val viewModel: BudgetsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()

    BudgetsContent(
        state = state,
        onBack = { navController.popBackStack() },
        onAddBudget = viewModel::addBudget,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun BudgetsContent(
    state: BudgetsUiState,
    onBack: () -> Unit,
    onAddBudget: (categoryId: String, amountCents: Long) -> Unit,
) {
    var showAddDialog by remember { mutableStateOf(false) }
    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Budgets · ${state.monthLabel}") })
        },
        floatingActionButton = {
            if (!state.loading && state.categories.isNotEmpty()) {
                FloatingActionButton(onClick = { showAddDialog = true }) {
                    Icon(Icons.Default.Add, contentDescription = "Add budget")
                }
            }
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
                state.rows.isEmpty() -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    Text("No budgets set for ${state.monthLabel}.")
                }
                else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                    items(state.rows.size) { i -> BudgetRowCard(state.rows[i]) }
                }
            }
        }
    }

    if (showAddDialog) {
        AddBudgetDialog(
            categories = state.categories,
            onDismiss = { showAddDialog = false },
            onConfirm = { categoryId, amountCents ->
                onAddBudget(categoryId, amountCents)
                showAddDialog = false
            },
        )
    }
}

@Composable
private fun BudgetRowCard(row: BudgetRow) {
    val over = row.spentCents > row.amountCents
    val channel =
        if (over) MagpieTheme.colors.overBudget.base else MagpieTheme.colors.underBudget.base
    val fraction =
        if (row.amountCents <= 0) 1f else (row.spentCents.toFloat() / row.amountCents).coerceIn(0f, 1f)
    PanelCard(channel = channel, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Column(modifier = Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(row.categoryName)
                Text("${formatCents(row.spentCents)} of ${formatCents(row.amountCents)}")
            }
            LinearProgressIndicator(
                progress = { fraction },
                color = channel,
                modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
            )
            val remaining = row.amountCents - row.spentCents
            Text(
                if (remaining >= 0) "${formatCents(remaining)} left" else "Over by ${formatCents(-remaining)}",
                style = MaterialTheme.typography.bodySmall,
                color = channel,
            )
        }
    }
}

@Composable
private fun AddBudgetDialog(
    categories: List<CategoryOut>,
    onDismiss: () -> Unit,
    onConfirm: (categoryId: String, amountCents: Long) -> Unit,
) {
    var selectedId by remember { mutableStateOf<String?>(null) }
    var amountText by remember { mutableStateOf("") }
    val amountCents = amountText.toDoubleOrNull()?.let { (it * 100).toLong() }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add budget") },
        text = {
            Column {
                TextField(
                    value = amountText,
                    onValueChange = { amountText = it },
                    label = { Text("Monthly amount") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.fillMaxWidth(),
                )
                Column(modifier = Modifier.heightIn(max = 240.dp).verticalScroll(rememberScrollState())) {
                    categories.forEach { category ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { selectedId = category.id }
                                .padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            RadioButton(
                                selected = selectedId == category.id,
                                onClick = { selectedId = category.id },
                            )
                            Text(category.name)
                        }
                    }
                }
            }
        },
        confirmButton = {
            PulseButton(
                text = "Save",
                enabled = selectedId != null && amountCents != null && amountCents > 0,
                compact = true,
                onClick = {
                    val id = selectedId
                    if (id != null && amountCents != null) onConfirm(id, amountCents)
                },
            )
        },
        dismissButton = {
            PulseButton(text = "Cancel", tonal = true, compact = true, onClick = onDismiss)
        },
    )
}
