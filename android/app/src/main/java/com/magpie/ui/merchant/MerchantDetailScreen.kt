package com.magpie.ui.merchant

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
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Storefront
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.TransactionOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.ui.util.RefreshOnResume
import com.magpie.util.formatCents
import design.pulse.ui.components.DataText
import design.pulse.ui.components.EmptyState
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.SectionHeader
import design.pulse.ui.theme.Pulse
import kotlin.math.abs

/** Thin ViewModel-wired wrapper. [MerchantDetailContent] below is the pure, screenshot half. */
@Composable
fun MerchantDetailScreen(navController: NavController, merchant: String) {
    val viewModel: MerchantDetailViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load(merchant) }

    MerchantDetailContent(state = state, onBack = { navController.popBackStack() })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun MerchantDetailContent(state: MerchantDetailUiState, onBack: () -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(state.merchant, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        when {
            state.loading -> Box(Modifier.padding(padding).fillMaxSize(), Alignment.Center) {
                CircularProgressIndicator()
            }
            state.error != null -> Box(Modifier.padding(padding).fillMaxSize(), Alignment.Center) {
                EmptyState(
                    icon = Icons.Default.Refresh,
                    title = "Couldn't load ${state.merchant}",
                    subtitle = state.error,
                )
            }
            state.transactions.isEmpty() -> Box(Modifier.padding(padding).fillMaxSize(), Alignment.Center) {
                EmptyState(
                    icon = Icons.Default.Storefront,
                    title = "Nothing here yet",
                    subtitle = "No spend recorded at ${state.merchant}.",
                )
            }
            else -> LazyColumn(
                modifier = Modifier.padding(padding).fillMaxSize().padding(MagpieTheme.spacing.md),
                verticalArrangement = Arrangement.spacedBy(MagpieTheme.spacing.sm),
            ) {
                item { MerchantSummaryCard(state) }
                items(state.transactions) { txn -> TransactionRow(txn) }
            }
        }
    }
}

@Composable
private fun MerchantSummaryCard(state: MerchantDetailUiState) {
    val money = MagpieTheme.colors.money.base
    PanelCard(channel = money, modifier = Modifier.fillMaxWidth()) {
        Column {
            SectionHeader(label = "Total spent", channel = money)
            DataText(formatCents(-abs(state.totalCents)), style = Pulse.dataType.dataMedium, color = money)
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(MagpieTheme.spacing.lg),
            ) {
                Column {
                    Text("Transactions", style = MaterialTheme.typography.labelSmall)
                    Text("${state.count}", style = MaterialTheme.typography.bodyLarge)
                }
                Column {
                    Text("Average", style = MaterialTheme.typography.labelSmall)
                    Text(formatCents(state.averageCents), style = MaterialTheme.typography.bodyLarge)
                }
            }
        }
    }
}

@Composable
private fun TransactionRow(txn: TransactionOut) {
    // Spend is neutral, income green (#31 grammar) — the same convention as the Transactions screen.
    val color =
        if (txn.kind == "income") MagpieTheme.colors.underBudget.base
        else MaterialTheme.colorScheme.onSurface
    PanelCard(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(txn.merchantRaw ?: txn.merchantNorm ?: "—", maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(txn.date, style = MaterialTheme.typography.bodySmall)
            }
            Text(formatCents(txn.amount), color = color)
        }
    }
}
