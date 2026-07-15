package com.magpie.ui.insight

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.BudgetVerdictOut
import com.magpie.data.remote.CategoryChangeOut
import com.magpie.data.remote.MonthlyInsightOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.Caption
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.SectionHeader
import kotlin.math.abs

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InsightScreen(navController: NavController) {
    val viewModel: InsightViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Your month", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            val insight = state.insight
            when {
                state.loading -> CircularProgressIndicator(Modifier.align(Alignment.Center))
                insight == null -> Text(
                    "No insight yet for ${state.monthLabel}.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                )
                else -> InsightContent(state.monthLabel, insight)
            }
        }
    }
}

@Composable
internal fun InsightContent(monthLabel: String, insight: MonthlyInsightOut) {
    val colors = MagpieTheme.colors
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // The AI narrative, when the model produced one — in its violet voice.
        val summary = insight.narrativeSummary?.takeIf { it.isNotBlank() }
        if (summary != null || insight.narrativeHeadline != null) {
            PanelCard(Modifier.fillMaxWidth()) {
                Column {
                    Caption(monthLabel)
                    Spacer(Modifier.height(6.dp))
                    insight.narrativeHeadline?.let { head ->
                        Text(
                            head,
                            style = MaterialTheme.typography.titleMedium,
                            color = if (insight.narrativeSource == "llm") colors.aiVoice.base
                                    else MaterialTheme.colorScheme.onSurface,
                        )
                        Spacer(Modifier.height(6.dp))
                    }
                    summary?.let {
                        Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }

        // In / out / net.
        PanelCard(Modifier.fillMaxWidth()) {
            Row(Modifier.fillMaxWidth()) {
                Stat("In", formatCents(insight.incomeCents), colors.money.base, Modifier.weight(1f))
                Stat("Out", formatCents(-abs(insight.spendCents)), MaterialTheme.colorScheme.onSurface, Modifier.weight(1f))
                Stat(
                    "Net",
                    formatCents(insight.netCents),
                    if (insight.netCents >= 0) colors.underBudget.base else colors.overBudget.base,
                    Modifier.weight(1f),
                )
            }
        }

        // Where spending moved vs the usual (trailing median).
        val changes = insight.categoryChanges
            .filter { it.deltaCents != 0L }
            .sortedByDescending { abs(it.deltaCents) }
            .take(8)
        if (changes.isNotEmpty()) {
            PanelCard(Modifier.fillMaxWidth()) {
                Column {
                    SectionHeader("Spending vs usual", channel = colors.money.base)
                    Spacer(Modifier.height(8.dp))
                    changes.forEach { ChangeRow(it, colors.overBudget.base, colors.underBudget.base) }
                }
            }
        }

        // How the month landed against budgets.
        if (insight.budgetVerdicts.isNotEmpty()) {
            PanelCard(Modifier.fillMaxWidth()) {
                Column {
                    SectionHeader("Budgets", channel = colors.money.base)
                    Spacer(Modifier.height(8.dp))
                    insight.budgetVerdicts.forEach { VerdictRow(it, colors.overBudget.base, colors.underBudget.base) }
                }
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: String, color: androidx.compose.ui.graphics.Color, modifier: Modifier) {
    Column(modifier) {
        Caption(label)
        Text(value, style = MaterialTheme.typography.titleMedium, color = color)
    }
}

@Composable
private fun ChangeRow(
    change: CategoryChangeOut,
    moreColor: androidx.compose.ui.graphics.Color,
    lessColor: androidx.compose.ui.graphics.Color,
) {
    val more = change.deltaCents > 0
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(change.category, style = MaterialTheme.typography.bodyLarge)
            Caption("usually ${formatCents(-abs(change.trailingMedianCents))}")
        }
        Text(
            (if (more) "+" else "−") + formatCents(abs(change.deltaCents)).removePrefix("-") + (if (more) " more" else " less"),
            style = MaterialTheme.typography.bodyMedium,
            color = if (more) moreColor else lessColor,
            textAlign = TextAlign.End,
        )
    }
}

@Composable
private fun VerdictRow(
    verdict: BudgetVerdictOut,
    overColor: androidx.compose.ui.graphics.Color,
    okColor: androidx.compose.ui.graphics.Color,
) {
    val over = verdict.overCents > 0
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(verdict.category, style = MaterialTheme.typography.bodyLarge)
            Caption("${formatCents(-abs(verdict.actualCents))} of ${formatCents(-abs(verdict.budgetCents))}")
        }
        Text(
            if (over) "over by ${formatCents(abs(verdict.overCents)).removePrefix("-")}" else "on track",
            style = MaterialTheme.typography.bodyMedium,
            color = if (over) overColor else okColor,
            textAlign = TextAlign.End,
        )
    }
}
