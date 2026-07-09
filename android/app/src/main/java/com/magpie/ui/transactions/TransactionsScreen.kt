package com.magpie.ui.transactions

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import com.magpie.util.formatCents
import design.pulse.ui.components.PanelCard

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun TransactionsScreen(navController: NavController) {
    val viewModel: TransactionsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Transactions") })
        },
    ) { padding ->
        when (val s = state) {
            is TransactionsUiState.Loading -> Box(
                Modifier.fillMaxSize().padding(padding),
                Alignment.Center,
            ) { CircularProgressIndicator() }

            is TransactionsUiState.Error -> Box(
                Modifier.fillMaxSize().padding(padding),
                Alignment.Center,
            ) { Text(s.message, color = MaterialTheme.colorScheme.error) }

            is TransactionsUiState.Ready -> {
                if (s.transactions.isEmpty()) {
                    Box(Modifier.fillMaxSize().padding(padding), Alignment.Center) {
                        Text("No transactions yet.")
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.padding(padding).padding(MagpieTheme.spacing.md),
                    ) {
                        items(s.transactions, key = { it.id }) { txn -> TransactionRow(txn) }
                    }
                }
            }
        }
    }
}

@Composable
private fun TransactionRow(txn: TransactionOut) {
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
                Text(txn.date, style = MaterialTheme.typography.bodySmall)
            }
            Text(formatCents(txn.amount), color = amountColor)
        }
    }
}
