package com.magpie.ui.transactions

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.TransactionOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.ui.util.RefreshOnResume
import com.magpie.util.formatCents
import design.pulse.ui.components.PanelCard

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransactionsScreen(navController: NavController) {
    val viewModel: TransactionsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }
    TransactionsContent(state = state, onSetFilter = viewModel::setFilter)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun TransactionsContent(
    state: TransactionsUiState,
    onSetFilter: (TxnFilter) -> Unit,
) {
    Scaffold(topBar = { TopAppBar(title = { Text("Transactions") }) }) { padding ->
        when (val s = state) {
            is TransactionsUiState.Loading -> Box(
                Modifier.fillMaxSize().padding(padding), Alignment.Center,
            ) { CircularProgressIndicator() }

            is TransactionsUiState.Error -> Box(
                Modifier.fillMaxSize().padding(padding), Alignment.Center,
            ) { Text(s.message, color = MaterialTheme.colorScheme.error) }

            is TransactionsUiState.Ready -> Column(Modifier.padding(padding).fillMaxSize()) {
                FilterRow(selected = s.filter, onSelect = onSetFilter)
                val visible = s.visible
                when {
                    s.all.isEmpty() -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                        Text("No transactions yet.")
                    }
                    visible.isEmpty() -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                        Text("Nothing matches “${s.filter.label}”.")
                    }
                    else -> LazyColumn(
                        modifier = Modifier.padding(horizontal = MagpieTheme.spacing.md),
                    ) {
                        items(visible, key = { it.id }) { txn ->
                            TransactionRow(txn, s.categoryNamesById[txn.categoryId])
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun FilterRow(selected: TxnFilter, onSelect: (TxnFilter) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = MagpieTheme.spacing.md, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        TxnFilter.entries.forEach { filter ->
            FilterChip(
                selected = selected == filter,
                onClick = { onSelect(filter) },
                label = { Text(filter.label) },
            )
        }
    }
}

@Composable
private fun TransactionRow(txn: TransactionOut, categoryName: String?) {
    // Color grammar (#31): ordinary spend is neutral — red is reserved for real deviations, not
    // the app's most common row. Only income gets the green channel; everything else stays neutral.
    val isIncome = txn.kind == "income"
    val accent = if (isIncome) MagpieTheme.colors.underBudget.base else null
    val amountColor =
        if (isIncome) MagpieTheme.colors.underBudget.base else MaterialTheme.colorScheme.onSurface
    PanelCard(channel = accent, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(txn.merchantRaw ?: txn.kind.replaceFirstChar { it.uppercase() })
                Text(
                    listOfNotNull(txn.date, categoryName).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Text(formatCents(txn.amount), color = amountColor)
        }
    }
}
