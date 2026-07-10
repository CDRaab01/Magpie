package com.magpie.ui.subscriptions

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
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Autorenew
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
import com.magpie.data.remote.SubscriptionOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.ui.util.RefreshOnResume
import com.magpie.util.formatCents
import design.pulse.ui.components.DataText
import design.pulse.ui.components.EmptyState
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.SectionHeader
import design.pulse.ui.theme.Pulse

/** Thin ViewModel-wired wrapper. [SubscriptionsContent] below is the pure, screenshot-testable half. */
@Composable
fun SubscriptionsScreen(navController: NavController) {
    val viewModel: SubscriptionsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }
    SubscriptionsContent(state = state, onBack = { navController.popBackStack() })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun SubscriptionsContent(state: SubscriptionsUiState, onBack: () -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Recurring") },
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
                Text(it, color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(MagpieTheme.spacing.md))
            }
            when {
                state.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    CircularProgressIndicator()
                }
                state.subscriptions.isEmpty() -> EmptyState(
                    icon = Icons.Default.Autorenew,
                    title = "No recurring charges found",
                    subtitle = "Magpie spots these once a charge repeats on a steady schedule.",
                )
                else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                    item { AnnualTotalCard(state.totalAnnualCostCents) }
                    items(state.subscriptions) { sub -> SubscriptionCard(sub) }
                }
            }
        }
    }
}

/** The headline number: what every recurring charge adds up to in a year — the reason this screen
 *  is "the single most actionable screen in consumer finance". */
@Composable
private fun AnnualTotalCard(totalAnnualCents: Long) {
    val channel = MagpieTheme.colors.money.base
    PanelCard(channel = channel, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Column {
            SectionHeader(label = "Recurring, per year", channel = channel)
            Spacer(Modifier.height(6.dp))
            DataText(text = formatCents(-totalAnnualCents), style = Pulse.dataType.dataLarge,
                color = channel)
        }
    }
}

@Composable
private fun SubscriptionCard(sub: SubscriptionOut) {
    // A charge above its usual is flagged (the price-hike signal, #22); teal otherwise.
    val hiked = sub.lastAmountCents > sub.typicalAmountCents * 11 / 10
    val channel = if (hiked) MagpieTheme.colors.overBudget.base else MagpieTheme.colors.money.base
    PanelCard(channel = channel, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(sub.merchant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    "${formatCents(-sub.typicalAmountCents)} ${sub.cadence}" +
                        if (hiked) " · went up" else "",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (hiked) channel else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                DataText(text = formatCents(-sub.annualCostCents), style = Pulse.dataType.dataSmall,
                    color = channel)
                Text("per year", style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
