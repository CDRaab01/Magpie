package com.magpie.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.ui.navigation.Routes
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader
import design.pulse.ui.components.StatTile

/** Thin ViewModel-wired wrapper. [HomeContent] below is the pure, screenshot-testable half. */
@Composable
fun HomeScreen(navController: NavController) {
    val viewModel: HomeViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()

    HomeContent(
        state = state,
        onAddTransaction = { navController.navigate(Routes.CASH_ENTRY) },
        onViewTransactions = { navController.navigate(Routes.TRANSACTIONS) },
        onViewAccounts = { navController.navigate(Routes.ACCOUNTS) },
        onCreateFirstAccount = viewModel::createFirstAccount,
    )
}

@Composable
internal fun HomeContent(
    state: HomeUiState,
    onAddTransaction: () -> Unit,
    onViewTransactions: () -> Unit,
    onViewAccounts: () -> Unit,
    onCreateFirstAccount: (name: String, institution: String, type: String) -> Unit,
) {
    Scaffold(
        floatingActionButton = {
            if (state is HomeUiState.Ready) {
                FloatingActionButton(onClick = onAddTransaction) {
                    Icon(Icons.Default.Add, contentDescription = "Add transaction")
                }
            }
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(MagpieTheme.spacing.lg)
                .fillMaxSize(),
        ) {
            Text("Magpie", style = MaterialTheme.typography.headlineMedium)
            Spacer(Modifier.height(16.dp))

            when (state) {
                is HomeUiState.Loading -> Box(Modifier.fillMaxWidth(), Alignment.Center) {
                    CircularProgressIndicator()
                }
                is HomeUiState.NeedsAccount -> CreateFirstAccountForm(onCreate = onCreateFirstAccount)
                is HomeUiState.Error -> Text(state.message, color = MaterialTheme.colorScheme.error)
                is HomeUiState.Ready -> {
                    MonthPanel(state.summary)
                    Spacer(Modifier.height(16.dp))
                    PulseButton(text = "View transactions", tonal = true, onClick = onViewTransactions)
                    Spacer(Modifier.height(8.dp))
                    PulseButton(text = "Accounts", tonal = true, onClick = onViewAccounts)
                }
            }
        }
    }
}

@Composable
private fun MonthPanel(summary: MonthlySummaryOut) {
    PanelCard(channel = MagpieTheme.colors.money.base) {
        SectionHeader(label = "This month", channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(12.dp))
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatTile(
                label = "Income",
                value = formatCents(summary.incomeCents),
                channel = MagpieTheme.colors.underBudget.base,
                modifier = Modifier.weight(1f),
            )
            StatTile(
                label = "Spend",
                value = formatCents(summary.spendCents),
                channel = MagpieTheme.colors.overBudget.base,
                modifier = Modifier.weight(1f),
            )
            StatTile(
                label = "Net",
                value = formatCents(summary.netCents),
                channel = MagpieTheme.colors.money.base,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun CreateFirstAccountForm(onCreate: (name: String, institution: String, type: String) -> Unit) {
    var name by remember { mutableStateOf("") }
    var institution by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("depository") }

    PanelCard(channel = MagpieTheme.colors.money.base) {
        SectionHeader(label = "Add your first account", channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(12.dp))
        TextField(
            value = name,
            onValueChange = { name = it },
            label = { Text("Name (e.g. Checking)") },
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        TextField(
            value = institution,
            onValueChange = { institution = it },
            label = { Text("Institution (e.g. US Bank)") },
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        Text("Type", style = MaterialTheme.typography.labelMedium)
        Spacer(Modifier.height(4.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            PulseButton(
                text = "Depository",
                tonal = type != "depository",
                compact = true,
                onClick = { type = "depository" },
            )
            PulseButton(
                text = "Card",
                tonal = type != "card",
                compact = true,
                onClick = { type = "card" },
            )
        }
        Spacer(Modifier.height(16.dp))
        PulseButton(
            text = "Create account",
            enabled = name.isNotBlank() && institution.isNotBlank(),
            onClick = { onCreate(name, institution, type) },
        )
    }
}
