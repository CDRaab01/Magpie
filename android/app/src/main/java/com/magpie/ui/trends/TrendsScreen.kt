package com.magpie.ui.trends

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.CategorySummaryItem
import com.magpie.data.remote.MerchantSummaryItem
import com.magpie.data.remote.MonthSummaryOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.ui.util.RefreshOnResume
import com.magpie.util.formatCents
import com.magpie.util.formatCentsCompact
import design.pulse.ui.components.DataText
import design.pulse.ui.components.EmptyState
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.SectionHeader
import design.pulse.ui.components.Sparkline
import design.pulse.ui.components.StatTile
import design.pulse.ui.theme.Pulse
import kotlin.math.abs

/** Thin ViewModel-wired wrapper. [TrendsContent] below is the pure, screenshot-testable half. */
@Composable
fun TrendsScreen(navController: NavController) {
    val viewModel: TrendsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }

    TrendsContent(
        state = state,
        onBack = { navController.popBackStack() },
        onMerchantClick = { navController.navigate(com.magpie.ui.navigation.Routes.merchantDetail(it)) },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun TrendsContent(
    state: TrendsUiState,
    onBack: () -> Unit,
    onMerchantClick: (String) -> Unit = {},
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Trends · ${state.monthLabel}") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        val hasData = state.history.isNotEmpty() || state.categories.isNotEmpty()
        when {
            state.loading -> Box(Modifier.padding(padding).fillMaxSize(), Alignment.Center) {
                CircularProgressIndicator()
            }
            state.error != null -> Box(Modifier.padding(padding).fillMaxSize(), Alignment.Center) {
                EmptyState(
                    icon = Icons.Default.Refresh,
                    title = "Couldn't load trends",
                    subtitle = state.error,
                )
            }
            !hasData -> Box(Modifier.padding(padding).fillMaxSize(), Alignment.Center) {
                EmptyState(
                    icon = Icons.Default.ShowChart,
                    title = "No spending yet",
                    subtitle = "Once transactions land, your monthly trends show up here.",
                )
            }
            else -> TrendsBody(state, onMerchantClick, Modifier.padding(padding))
        }
    }
}

@Composable
private fun TrendsBody(
    state: TrendsUiState,
    onMerchantClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().padding(MagpieTheme.spacing.md),
        verticalArrangement = Arrangement.spacedBy(MagpieTheme.spacing.sm),
    ) {
        if (state.history.isNotEmpty()) {
            item { NetTrendCard(state.history) }
            item { IncomeSpendTiles(state.history) }
        }
        if (state.categories.isNotEmpty()) {
            item { SectionHeader(label = "Top categories", channel = MagpieTheme.colors.money.base) }
            items(state.categories.filter { it.spendCents < 0 }.take(8)) { category ->
                CategoryRow(category, maxSpend = maxCategorySpend(state.categories))
            }
        }
        if (state.merchants.isNotEmpty()) {
            item { SectionHeader(label = "Top merchants", channel = MagpieTheme.colors.money.base) }
            items(state.merchants) { merchant ->
                MerchantRow(merchant, onClick = { onMerchantClick(merchant.merchant) })
            }
        }
    }
}

/** The headline: the latest month's net figure over a filled sparkline of the last N months. */
@Composable
private fun NetTrendCard(history: List<MonthSummaryOut>) {
    val money = MagpieTheme.colors.money.base
    val latest = history.last().netCents
    PanelCard(channel = money, modifier = Modifier.fillMaxWidth()) {
        Column {
            SectionHeader(label = "Net · last ${history.size} months", channel = money)
            Spacer(Modifier.height(8.dp))
            DataText(formatCents(latest), style = Pulse.dataType.dataMedium, color = money)
            Spacer(Modifier.height(12.dp))
            // Net can go negative, so keep a zero-relative shape (normalizeMinMax stays on for a
            // readable line even when all values cluster). The filled line is Spotter's idiom.
            Sparkline(
                values = history.map { it.netCents.toFloat() },
                channel = money,
                asBars = false,
                strokeWidth = 2.dp,
                modifier = Modifier.fillMaxWidth().height(56.dp),
            )
        }
    }
}

/** Income (green) and spend (neutral, per #31 grammar) as dense tiles with their own sparklines. */
@Composable
private fun IncomeSpendTiles(history: List<MonthSummaryOut>) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(MagpieTheme.spacing.sm),
    ) {
        StatTile(
            label = "Income",
            value = formatCentsCompact(history.last().incomeCents),
            channel = MagpieTheme.colors.underBudget.base,
            dense = true,
            sparkline = history.map { it.incomeCents.toFloat() },
            modifier = Modifier.weight(1f),
        )
        StatTile(
            label = "Spend",
            value = formatCentsCompact(history.last().spendCents),
            channel = MaterialTheme.colorScheme.onSurface,
            dense = true,
            // Spend is negative; use magnitudes so the bars read as "how much", not an inverted dip.
            sparkline = history.map { abs(it.spendCents.toFloat()) },
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun CategoryRow(category: CategorySummaryItem, maxSpend: Long) {
    val fraction =
        if (maxSpend <= 0) 0f else (abs(category.spendCents).toFloat() / maxSpend).coerceIn(0f, 1f)
    // Ordinary spend is neutral (#31): the bar is the money channel, never red.
    val channel = MagpieTheme.colors.money.base
    PanelCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    category.categoryName,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                Text(formatCents(category.spendCents), color = MaterialTheme.colorScheme.onSurface)
            }
            LinearProgressIndicator(
                progress = { fraction },
                color = channel,
                modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
            )
        }
    }
}

@Composable
private fun MerchantRow(merchant: MerchantSummaryItem, onClick: () -> Unit) {
    PanelCard(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(merchant.merchant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    "${merchant.transactionCount} " +
                        if (merchant.transactionCount == 1) "transaction" else "transactions",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(formatCents(merchant.spendCents), color = MaterialTheme.colorScheme.onSurface)
        }
    }
}

private fun maxCategorySpend(categories: List<CategorySummaryItem>): Long =
    categories.filter { it.spendCents < 0 }.minOfOrNull { it.spendCents }?.let { abs(it) } ?: 0L
