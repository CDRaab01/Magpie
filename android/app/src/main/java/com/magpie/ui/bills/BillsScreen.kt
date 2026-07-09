package com.magpie.ui.bills

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
import androidx.compose.material3.ExperimentalMaterial3Api
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
import com.magpie.data.remote.BillOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.PanelCard

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BillsScreen(navController: NavController) {
    val viewModel: BillsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()

    BillsContent(state = state, onBack = { navController.popBackStack() })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun BillsContent(state: BillsUiState, onBack: () -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Bills") })
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
                state.bills.isEmpty() -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    Text("No bills yet.")
                }
                else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                    items(state.bills, key = { it.id }) { bill -> BillRow(bill) }
                }
            }
        }
    }
}

@Composable
private fun BillRow(bill: BillOut) {
    val channel = when {
        bill.isMissing -> MagpieTheme.colors.overBudget.base
        bill.matchedTransactionId != null -> MagpieTheme.colors.underBudget.base
        else -> MagpieTheme.colors.money.base
    }
    PanelCard(channel = channel, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(bill.biller)
                Text("Due ${bill.dueDate}", style = MaterialTheme.typography.bodySmall)
                val status = when {
                    bill.isMissing -> "Missing"
                    bill.matchedTransactionId != null -> "Paid"
                    else -> "Awaiting payment"
                }
                Text(status, style = MaterialTheme.typography.bodySmall, color = channel)
            }
            Text(formatCents(-bill.amountDue), color = channel)
        }
    }
}
