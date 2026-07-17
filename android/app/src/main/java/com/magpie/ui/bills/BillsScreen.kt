package com.magpie.ui.bills

import androidx.compose.material.icons.filled.CalendarMonth
import design.pulse.ui.components.EmptyState
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
import com.magpie.ui.util.RefreshOnResume
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.StaleBanner

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BillsScreen(navController: NavController) {
    val viewModel: BillsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }

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
            // Offline read-cache indicator: the list below is the last-known snapshot. Bills is a
            // read-only screen, so there's nothing to disable — just the honesty banner.
            state.staleAsOfMs?.let {
                StaleBanner(
                    asOfMs = it,
                    channel = MagpieTheme.colors.needsReview.base,
                    modifier = Modifier.padding(horizontal = MagpieTheme.spacing.md, vertical = 4.dp),
                )
            }
            when {
                state.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    CircularProgressIndicator()
                }
                state.bills.isEmpty() -> EmptyState(
                    icon = Icons.Default.CalendarMonth,
                    title = "No bills yet",
                    subtitle = "Bill-due alerts and CSV imports show up here.",
                )
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
            // Color grammar (#31): color the status *word* (above), never the amount — a paid
            // bill's amount rendering green broke the sign grammar. The amount stays neutral.
            Text(formatCents(-bill.amountDue), color = MaterialTheme.colorScheme.onSurface)
        }
    }
}
