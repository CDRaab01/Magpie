package com.magpie.ui.budgets

import androidx.compose.material.icons.filled.PieChart
import design.pulse.ui.components.EmptyState
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.text.KeyboardOptions
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.CategoryAnalysisOut
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.CoachPlanOut
import com.magpie.data.remote.ProposedCutOut
import com.magpie.ui.util.RefreshOnResume
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.DataText
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.ProgressRing
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader
import design.pulse.ui.components.Sparkline
import design.pulse.ui.theme.Pulse

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BudgetsScreen(navController: NavController) {
    val viewModel: BudgetsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }

    BudgetsContent(
        state = state,
        onBack = { navController.popBackStack() },
        onAddBudget = viewModel::addBudget,
        onAcceptProposal = viewModel::acceptProposal,
        onSetGoal = viewModel::setGoal,
        onClearGoal = viewModel::clearGoal,
        onLoadPlan = viewModel::loadPlan,
        onDismissPlan = viewModel::dismissPlan,
        onApplyCut = viewModel::applyCut,
        onOpenCategory = viewModel::openCategory,
        onDismissAnalysis = viewModel::dismissAnalysis,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun BudgetsContent(
    state: BudgetsUiState,
    onBack: () -> Unit,
    onAddBudget: (categoryId: String, amountCents: Long) -> Unit,
    onAcceptProposal: (categoryId: String, amountCents: Long) -> Unit = { _, _ -> },
    onSetGoal: (amountCents: Long) -> Unit = {},
    onClearGoal: () -> Unit = {},
    onLoadPlan: () -> Unit = {},
    onDismissPlan: () -> Unit = {},
    onApplyCut: (ProposedCutOut) -> Unit = {},
    onOpenCategory: (categoryId: String) -> Unit = {},
    onDismissAnalysis: () -> Unit = {},
) {
    var showAddDialog by remember { mutableStateOf(false) }
    var showGoalDialog by remember { mutableStateOf(false) }
    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Budgets · ${state.monthLabel}") })
        },
        floatingActionButton = {
            if (!state.loading && state.categories.isNotEmpty()) {
                FloatingActionButton(onClick = { showAddDialog = true }) {
                    Icon(Icons.Default.Add, contentDescription = "Add budget")
                }
            }
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
                // Cold start: no budgets AND no drafts to confirm — the goal prompt still shows,
                // so the coach is reachable from an empty screen (prod starts here).
                state.rows.isEmpty() && state.proposals.isEmpty() ->
                    LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                        item {
                            GoalCard(state, onEdit = { showGoalDialog = true }, onLoadPlan = onLoadPlan)
                        }
                        item {
                            EmptyState(
                                icon = Icons.Default.PieChart,
                                title = "No budgets for ${state.monthLabel}",
                                subtitle = "Tap + to set a monthly amount per category.",
                            )
                        }
                    }
                else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                    item { GoalCard(state, onEdit = { showGoalDialog = true }, onLoadPlan = onLoadPlan) }
                    if (state.coachHeadline != null || state.coachCoaching != null) {
                        item { CoachCard(state.coachHeadline, state.coachCoaching) }
                    }
                    if (state.proposals.isNotEmpty()) {
                        item {
                            SectionHeader(
                                label = "Suggested from your spending",
                                channel = MagpieTheme.colors.money.base,
                            )
                        }
                        items(state.proposals.size) { i ->
                            BudgetSuggestionCard(state.proposals[i], onAcceptProposal)
                        }
                    }
                    if (state.rows.isNotEmpty()) {
                        item { BudgetsRingHeader(state.rows) }
                        items(state.rows.size) { i ->
                            BudgetRowCard(
                                state.rows[i],
                                daysLeft = state.daysLeft,
                                onClick = { onOpenCategory(state.rows[i].categoryId) },
                            )
                        }
                    }
                    if (state.uncategorizedMtdCents > 0) {
                        item { UncategorizedNote(state.uncategorizedMtdCents) }
                    }
                }
            }
        }
    }

    if (showAddDialog) {
        AddBudgetDialog(
            categories = state.categories,
            onDismiss = { showAddDialog = false },
            onConfirm = { categoryId, amountCents ->
                onAddBudget(categoryId, amountCents)
                showAddDialog = false
            },
        )
    }

    if (showGoalDialog) {
        GoalDialog(
            currentCents = state.goal?.amountCents,
            onDismiss = { showGoalDialog = false },
            onConfirm = { cents ->
                onSetGoal(cents)
                showGoalDialog = false
            },
            onClear = if (state.goal != null) {
                {
                    onClearGoal()
                    showGoalDialog = false
                }
            } else null,
        )
    }

    state.plan?.let { plan ->
        PlanSheet(plan = plan, onDismiss = onDismissPlan, onApplyCut = onApplyCut)
    }

    state.analysis?.let { analysis ->
        CategoryAnalysisSheet(analysis = analysis, onDismiss = onDismissAnalysis)
    }
}

/** The savings goal at the top of the screen: set it, see the projection against it, and reach
 *  the "how do I get there?" plan. On-track reads in the money channel; short reads over-budget
 *  red — the goal delta is the one number that carries the household's month. */
@Composable
private fun GoalCard(state: BudgetsUiState, onEdit: () -> Unit, onLoadPlan: () -> Unit) {
    val goal = state.goal
    val net = state.net
    val short = net?.goalDeltaCents?.let { it < 0 } ?: false
    val channel = if (short) MagpieTheme.colors.overBudget.base else MagpieTheme.colors.money.base
    PanelCard(channel = channel, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Column(modifier = Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                SectionHeader(label = "Savings goal", channel = channel)
                PulseButton(
                    text = if (goal == null) "Set goal" else "Edit",
                    tonal = true,
                    compact = true,
                    onClick = onEdit,
                )
            }
            Spacer(Modifier.height(6.dp))
            if (goal == null) {
                Text(
                    "Set a monthly savings target and Magpie coaches the month toward it.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                Text("${formatCents(goal.amountCents)}/month")
                if (net != null) {
                    val delta = net.goalDeltaCents ?: 0
                    Text(
                        "Projecting ${formatCents(net.projectedNetCents)} net — " +
                            if (delta >= 0) "${formatCents(delta)} ahead of goal"
                            else "${formatCents(-delta)} short",
                        style = MaterialTheme.typography.bodySmall,
                        color = channel,
                    )
                    Spacer(Modifier.height(6.dp))
                    PulseButton(
                        text = "How do I get there?",
                        tonal = true,
                        compact = true,
                        onClick = onLoadPlan,
                    )
                }
            }
        }
    }
}

/** The coach's voice — violet `aiVoice`, the established "the model said this" visual. Renders
 *  only when the local LLM actually produced coaching; deterministic facts never wear violet. */
@Composable
private fun CoachCard(headline: String?, coaching: String?) {
    val channel = MagpieTheme.colors.aiVoice.base
    PanelCard(channel = channel, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Column {
            SectionHeader(label = "Coach", channel = channel)
            Spacer(Modifier.height(6.dp))
            headline?.let { Text(it, style = MaterialTheme.typography.titleSmall) }
            coaching?.let {
                Spacer(Modifier.height(4.dp))
                Text(it, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

/** Coaching accuracy is honest: spend without a category is invisible to per-category pace. */
@Composable
private fun UncategorizedNote(cents: Long) {
    Text(
        "${formatCents(cents)} of this month's spend has no category yet — review it for " +
            "sharper coaching.",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(vertical = 8.dp),
    )
}

/**
 * Overall month-utilization ring (Wave 1 #15) — Plate's hero-ring pattern in Magpie's teal: total
 * spent across every budgeted category over total budget. Teal (money) normally, red only when the
 * household is genuinely over its combined budget (#31 grammar — the ring, not every row, carries
 * the alarm).
 */
@Composable
private fun BudgetsRingHeader(rows: List<BudgetRow>) {
    val totalBudget = rows.sumOf { it.amountCents }
    val totalSpent = rows.sumOf { it.spentCents }
    val over = totalSpent > totalBudget
    val channel = if (over) MagpieTheme.colors.overBudget.base else MagpieTheme.colors.money.base
    val fraction =
        if (totalBudget <= 0) 0f else (totalSpent.toFloat() / totalBudget).coerceIn(0f, 1f)
    val pct = if (totalBudget <= 0) 0 else ((totalSpent * 100) / totalBudget).toInt()
    PanelCard(
        channel = channel,
        modifier = Modifier.fillMaxWidth().padding(bottom = MagpieTheme.spacing.sm),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(MagpieTheme.spacing.md),
        ) {
            ProgressRing(progress = fraction, channel = channel, modifier = Modifier.size(96.dp)) {
                DataText("$pct%", style = Pulse.dataType.dataSmall, color = channel)
            }
            Column {
                SectionHeader(label = "This month", channel = channel)
                Text("${formatCents(totalSpent)} of ${formatCents(totalBudget)}")
                val remaining = totalBudget - totalSpent
                Text(
                    if (remaining >= 0) "${formatCents(remaining)} left"
                    else "Over by ${formatCents(-remaining)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = channel,
                )
            }
        }
    }
}

/** A "set budgets from your history" draft (#17): the category, its trailing-median spend, and a
 *  Set button that turns the suggestion into a real budget — review, not enter. */
@Composable
private fun BudgetSuggestionCard(proposal: BudgetProposal, onAccept: (String, Long) -> Unit) {
    PanelCard(
        channel = MagpieTheme.colors.money.base,
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(proposal.categoryName)
                Text(
                    "Typically ${formatCents(proposal.suggestedAmountCents)}/mo",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            PulseButton(
                text = "Set ${formatCents(proposal.suggestedAmountCents)}",
                tonal = true,
                compact = true,
                onClick = { onAccept(proposal.categoryId, proposal.suggestedAmountCents) },
            )
        }
    }
}

@Composable
private fun BudgetRowCard(row: BudgetRow, daysLeft: Int?, onClick: () -> Unit) {
    val over = row.spentCents > row.amountCents
    // Pace-aware channel when the coach status loaded; the plain over/under grammar otherwise.
    val channel = when (row.paceStatus) {
        "over", "over_pace" -> MagpieTheme.colors.overBudget.base
        "watch" -> MagpieTheme.colors.needsReview.base
        "on_track", "early" -> MagpieTheme.colors.underBudget.base
        else ->
            if (over) MagpieTheme.colors.overBudget.base else MagpieTheme.colors.underBudget.base
    }
    val fraction =
        if (row.amountCents <= 0) 1f else (row.spentCents.toFloat() / row.amountCents).coerceIn(0f, 1f)
    PanelCard(
        channel = channel,
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).clickable(onClick = onClick),
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(row.categoryName)
                Text("${formatCents(row.spentCents)} of ${formatCents(row.amountCents)}")
            }
            LinearProgressIndicator(
                progress = { fraction },
                color = channel,
                modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
            )
            val remaining = row.amountCents - row.spentCents
            Text(
                if (remaining >= 0) "${formatCents(remaining)} left" else "Over by ${formatCents(-remaining)}",
                style = MaterialTheme.typography.bodySmall,
                color = channel,
            )
            // The coach's pace line: projection + the daily spend that lands exactly on budget.
            if (row.projectedCents != null) {
                val allowance = row.dailyAllowanceCents ?: 0
                Text(
                    "On pace for ${formatCents(row.projectedCents)}" +
                        if (allowance > 0 && (daysLeft ?: 0) > 0) {
                            " · ${formatCents(allowance)}/day keeps it on budget"
                        } else "",
                    style = MaterialTheme.typography.bodySmall,
                    color = channel,
                )
            }
        }
    }
}

/** The "what would need to change" plan: each cut is one draft — Apply PATCHes that budget. The
 *  shortfall line is honest when the plan can't reach the target without touching fixed bills. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PlanSheet(
    plan: CoachPlanOut,
    onDismiss: () -> Unit,
    onApplyCut: (ProposedCutOut) -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
            SectionHeader(label = "Getting to ${formatCents(plan.targetCents)}/mo", channel = MagpieTheme.colors.money.base)
            Spacer(Modifier.height(6.dp))
            if (plan.neededCents <= 0) {
                Text(
                    "You're already on target: baseline net is ${formatCents(plan.baselineNetCents)}/mo.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            } else {
                Text(
                    "Baseline net ${formatCents(plan.baselineNetCents)}/mo — " +
                        "${formatCents(plan.neededCents)} to find. Each cut is a draft; apply the " +
                        "ones you want.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (plan.narrativeSource == "llm" && plan.narrativeCoaching != null) {
                Spacer(Modifier.height(8.dp))
                CoachCard(plan.narrativeHeadline, plan.narrativeCoaching)
            }
            Spacer(Modifier.height(8.dp))
            plan.cuts.forEach { cut ->
                PanelCard(
                    channel = MagpieTheme.colors.money.base,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(cut.categoryName)
                            Text(
                                "${formatCents(cut.fromCents)} → ${formatCents(cut.toCents)}" +
                                    " (saves ${formatCents(cut.cutCents)}/mo)",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        PulseButton(
                            text = "Apply",
                            tonal = true,
                            compact = true,
                            onClick = { onApplyCut(cut) },
                        )
                    }
                }
            }
            if (plan.shortfallCents > 0) {
                Text(
                    "Even with every cut, this plan is ${formatCents(plan.shortfallCents)}/mo short " +
                        "— bills don't leave more room.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MagpieTheme.colors.needsReview.base,
                    modifier = Modifier.padding(vertical = 8.dp),
                )
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

/** One category in depth: trend, budget-vs-actual history, where the money went, and the coach's
 *  read on it (violet, only when the model spoke). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CategoryAnalysisSheet(analysis: CategoryAnalysisOut, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .padding(MagpieTheme.spacing.md)
                .verticalScroll(rememberScrollState()),
        ) {
            SectionHeader(label = analysis.categoryName, channel = MagpieTheme.colors.money.base)
            Spacer(Modifier.height(6.dp))
            Text(
                "${formatCents(analysis.spentCents)} this month" +
                    (analysis.budgetCents?.let { " of a ${formatCents(it)} budget" } ?: "") +
                    " · usually ${formatCents(analysis.trailingMedianCents)}/mo",
                style = MaterialTheme.typography.bodyMedium,
            )
            analysis.pace?.let { pace ->
                if (pace.projectedCents != null) {
                    Text(
                        "On pace for ${formatCents(pace.projectedCents)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (analysis.monthlyHistory.size >= 2) {
                Spacer(Modifier.height(10.dp))
                Sparkline(
                    values = analysis.monthlyHistory.map { it.spendCents.toFloat() },
                    channel = MagpieTheme.colors.money.base,
                )
                Text(
                    "Last ${analysis.monthlyHistory.size} months",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (analysis.narrativeSource == "llm" && analysis.narrativeCoaching != null) {
                Spacer(Modifier.height(8.dp))
                CoachCard(analysis.narrativeHeadline, analysis.narrativeCoaching)
            }
            if (analysis.topMerchants.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                SectionHeader(label = "Where it went", channel = MagpieTheme.colors.money.base)
                Spacer(Modifier.height(4.dp))
                analysis.topMerchants.forEach { m ->
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(
                            "${m.merchant} ×${m.count}",
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.weight(1f),
                        )
                        Text(formatCents(m.spendCents), style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun GoalDialog(
    currentCents: Long?,
    onDismiss: () -> Unit,
    onConfirm: (amountCents: Long) -> Unit,
    onClear: (() -> Unit)?,
) {
    var amountText by remember {
        mutableStateOf(currentCents?.let { "%.2f".format(it / 100.0) } ?: "")
    }
    val amountCents = amountText.toDoubleOrNull()?.let { (it * 100).toLong() }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Monthly savings goal") },
        text = {
            Column {
                Text(
                    "How much should be left over each month after spending?",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(8.dp))
                TextField(
                    value = amountText,
                    onValueChange = { amountText = it },
                    label = { Text("Amount (e.g. 500)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            PulseButton(
                text = "Save",
                enabled = amountCents != null && amountCents > 0,
                compact = true,
                onClick = { amountCents?.let(onConfirm) },
            )
        },
        dismissButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (onClear != null) {
                    PulseButton(text = "Remove goal", tonal = true, compact = true, onClick = onClear)
                }
                PulseButton(text = "Cancel", tonal = true, compact = true, onClick = onDismiss)
            }
        },
    )
}

@Composable
private fun AddBudgetDialog(
    categories: List<CategoryOut>,
    onDismiss: () -> Unit,
    onConfirm: (categoryId: String, amountCents: Long) -> Unit,
) {
    var selectedId by remember { mutableStateOf<String?>(null) }
    var amountText by remember { mutableStateOf("") }
    val amountCents = amountText.toDoubleOrNull()?.let { (it * 100).toLong() }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add budget") },
        text = {
            Column {
                TextField(
                    value = amountText,
                    onValueChange = { amountText = it },
                    label = { Text("Monthly amount") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.fillMaxWidth(),
                )
                Column(modifier = Modifier.heightIn(max = 240.dp).verticalScroll(rememberScrollState())) {
                    categories.forEach { category ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { selectedId = category.id }
                                .padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            RadioButton(
                                selected = selectedId == category.id,
                                onClick = { selectedId = category.id },
                            )
                            Text(category.name)
                        }
                    }
                }
            }
        },
        confirmButton = {
            PulseButton(
                text = "Save",
                enabled = selectedId != null && amountCents != null && amountCents > 0,
                compact = true,
                onClick = {
                    val id = selectedId
                    if (id != null && amountCents != null) onConfirm(id, amountCents)
                },
            )
        },
        dismissButton = {
            PulseButton(text = "Cancel", tonal = true, compact = true, onClick = onDismiss)
        },
    )
}
