package com.magpie.ui.cashflow

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
import com.magpie.data.remote.CashflowCalendarOut
import com.magpie.ui.util.RefreshOnResume
import com.magpie.data.remote.UpcomingBillOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.PanelCard

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CashflowScreen(navController: NavController) {
    val viewModel: CashflowViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }

    CashflowContent(state = state, onBack = { navController.popBackStack() })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun CashflowContent(state: CashflowUiState, onBack: () -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Cash flow") },
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
            val calendar = state.calendar
            when {
                state.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    CircularProgressIndicator()
                }
                calendar == null -> Unit
                else -> CashflowBody(calendar)
            }
        }
    }
}

@Composable
private fun CashflowBody(calendar: CashflowCalendarOut) {
    val before = calendar.bills.filter { it.beforeNextPaycheck }
    val after = calendar.bills.filterNot { it.beforeNextPaycheck }
    LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
        item { PaycheckHeader(calendar) }
        if (calendar.bills.isEmpty()) {
            item {
                Box(Modifier.fillMaxWidth().padding(top = MagpieTheme.spacing.lg), Alignment.Center) {
                    Text("Nothing due — no upcoming bills.")
                }
            }
        }
        if (before.isNotEmpty()) {
            item { SectionLabel("Due before next paycheck") }
            items(before.size) { i -> BillRow(before[i]) }
        }
        if (after.isNotEmpty()) {
            item { SectionLabel("After payday") }
            items(after.size) { i -> BillRow(after[i]) }
        }
    }
}

@Composable
private fun PaycheckHeader(calendar: CashflowCalendarOut) {
    PanelCard(
        channel = MagpieTheme.colors.money.base,
        modifier = Modifier.fillMaxWidth().padding(bottom = MagpieTheme.spacing.sm),
    ) {
        Column {
            val paycheck = calendar.nextPaycheckDate
            Text(
                if (paycheck != null) "Next paycheck $paycheck" else "No paycheck scheduled",
                style = MaterialTheme.typography.bodyMedium,
            )
            Text(
                "Due before then: ${formatCents(-calendar.totalDueBeforePaycheckCents)}",
                style = MaterialTheme.typography.headlineSmall,
                color = MagpieTheme.colors.money.base,
            )
        }
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.labelLarge,
        modifier = Modifier.padding(top = MagpieTheme.spacing.md, bottom = 4.dp),
    )
}

@Composable
private fun BillRow(bill: UpcomingBillOut) {
    // Corrected color grammar (ARCHITECTURE.md Tier 4): red only for the real deviation (overdue),
    // amber for the "handle soon" set, teal/money otherwise — never red on an ordinary upcoming bill.
    val channel = when {
        bill.isOverdue -> MagpieTheme.colors.overBudget.base
        bill.beforeNextPaycheck -> MagpieTheme.colors.needsReview.base
        else -> MagpieTheme.colors.money.base
    }
    PanelCard(channel = channel, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(bill.biller)
                Text(
                    "Due ${bill.dueDate} · ${bill.accountName}",
                    style = MaterialTheme.typography.bodySmall,
                )
                if (bill.isOverdue) {
                    Text("Overdue", style = MaterialTheme.typography.bodySmall, color = channel)
                }
            }
            Text(formatCents(-bill.amountDueCents))
        }
    }
}
