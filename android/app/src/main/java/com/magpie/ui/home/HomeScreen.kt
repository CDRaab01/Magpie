package com.magpie.ui.home

import androidx.compose.material.icons.filled.Refresh
import design.pulse.ui.components.EmptyState
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.MonthlyInsightOut
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.ui.util.RefreshOnResume
import com.magpie.ui.navigation.Routes
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import com.magpie.util.formatCentsCompact
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader
import design.pulse.ui.components.Sparkline
import design.pulse.ui.components.StaleBanner
import design.pulse.ui.components.TickerNumber
import design.pulse.ui.theme.Pulse

/** Thin ViewModel-wired wrapper. [HomeContent] below is the pure, screenshot-testable half. */
@Composable
fun HomeScreen(navController: NavController) {
    val viewModel: HomeViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }

    HomeContent(
        state = state,
        onAddTransaction = { navController.navigate(Routes.CASH_ENTRY) },
        onViewAccounts = { navController.navigate(Routes.ACCOUNTS) },
        onViewReviewQueue = { navController.navigate(Routes.REVIEW_QUEUE) },
        onViewCashflow = { navController.navigate(Routes.CASHFLOW) },
        onViewFlow = { navController.navigate(Routes.FLOW) },
        onViewInsight = { navController.navigate(Routes.INSIGHT) },
        onViewRules = { navController.navigate(Routes.RULES) },
        onViewTrends = { navController.navigate(Routes.TRENDS) },
        onAskMagpie = { navController.navigate(Routes.CHAT) },
        onCreateFirstAccount = viewModel::createFirstAccount,
    )
}

@Composable
internal fun HomeContent(
    state: HomeUiState,
    onAddTransaction: () -> Unit,
    onViewAccounts: () -> Unit,
    onViewReviewQueue: () -> Unit,
    onViewCashflow: () -> Unit,
    onViewFlow: () -> Unit = {},
    onViewInsight: () -> Unit = {},
    onViewRules: () -> Unit,
    onViewTrends: () -> Unit,
    onAskMagpie: () -> Unit = {},
    onCreateFirstAccount: (name: String, institution: String, type: String, last4: String?) -> Unit,
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
            if (state is HomeUiState.Ready) {
                MagpieHero(state, onClick = onViewCashflow)
                // The offline read-cache indicator (#B): shown only when Home was restored from the
                // last-known snapshot because the tailnet was unreachable — stale-but-real, with the
                // capture time. Hidden entirely when online. Pulse's shared banner, in Magpie's
                // needs-review amber (Pulse knows hues, Magpie binds the meaning).
                state.asOfMs?.let {
                    StaleBanner(
                        asOfMs = it,
                        channel = MagpieTheme.colors.needsReview.base,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
            } else {
                Text("Magpie", style = MaterialTheme.typography.headlineMedium)
            }
            Spacer(Modifier.height(16.dp))

            when (state) {
                is HomeUiState.Loading -> Box(Modifier.fillMaxWidth(), Alignment.Center) {
                    CircularProgressIndicator()
                }
                is HomeUiState.NeedsAccount -> CreateFirstAccountForm(onCreate = onCreateFirstAccount)
                is HomeUiState.Error -> EmptyState(
                    icon = Icons.Default.Refresh,
                    title = "Couldn't reach Magpie",
                    subtitle = state.message,
                )
                is HomeUiState.Ready -> {
                    MonthPanel(state.summary, state.history)
                    InsightCard(state.insight, onClick = onViewInsight)
                    Spacer(Modifier.height(12.dp))
                    AskMagpieCard(onClick = onAskMagpie)
                    Spacer(Modifier.height(12.dp))
                    // Content, not links (#29): the review queue and the next bill are live cards
                    // showing their own data; only the two non-tab utilities (Accounts, Rules) stay
                    // as compact secondary links.
                    ReviewQueueCard(count = state.reviewCount, onClick = onViewReviewQueue)
                    Spacer(Modifier.height(8.dp))
                    UpcomingBillCard(bill = state.nextBill, onClick = onViewCashflow)
                    Spacer(Modifier.height(16.dp))
                    Row(
                        modifier = Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        PulseButton(
                            text = "Accounts", tonal = true, compact = true, onClick = onViewAccounts,
                        )
                        PulseButton(
                            text = "Cash flow", tonal = true, compact = true, onClick = onViewFlow,
                        )
                        PulseButton(
                            text = "Trends", tonal = true, compact = true, onClick = onViewTrends,
                        )
                        PulseButton(
                            text = "Rules", tonal = true, compact = true, onClick = onViewRules,
                        )
                    }
                }
            }
        }
    }
}

/**
 * The Home hero (#28)  -  the personalized gradient panel every sibling opens with, using the
 * indigo→teal→green "magpie" gradient that was added to Pulse for this app but until now went
 * unused. Greeting + a one-line money status ("$3,180 net this month · 3 to review · XCEL due
 * Jul 18"), the finance analogue of Plate's "TRAINED TODAY" line.
 */
@Composable
private fun MagpieHero(state: HomeUiState.Ready, onClick: () -> Unit) {
    val white = androidx.compose.ui.graphics.Color.White
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(MagpieTheme.colors.heroGradient)
            .clickable(onClick = onClick)
            .padding(20.dp),
    ) {
        Column {
            // Sizes match Spotter's GreetingPanel  -  headlineMedium greeting, and a full-white
            // (not alpha'd) status line so the subtitle clears AA contrast on the hero gradient.
            Text(
                state.greeting,
                style = MaterialTheme.typography.headlineMedium,
                color = white,
            )
            // The headline number is NET THIS MONTH (income - spend so far): real money in vs out,
            // grounded and always meaningful. Safe-to-spend is a forward projection that reads as
            // noise until paychecks + bills are armed, so it moves to the secondary status line
            // rather than dominating the hero. Tapping the hero opens the cash-flow calendar.
            Spacer(Modifier.height(12.dp))
            Text(
                "NET THIS MONTH",
                style = MaterialTheme.typography.labelSmall,
                color = white.copy(alpha = 0.85f),
            )
            val netDollars = (state.summary.netCents / 100).toInt()
            TickerNumber(
                target = kotlin.math.abs(netDollars),
                prefix = if (netDollars < 0) "-$" else "$",
                style = MagpieTheme.dataType.dataLarge,
                color = white,
            )
            val status = heroStatusLine(state)
            if (status.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Text(
                    status,
                    style = MaterialTheme.typography.bodyLarge,
                    color = white,
                )
            }
        }
    }
}

private fun heroStatusLine(state: HomeUiState.Ready): String {
    val parts = mutableListOf<String>()
    state.safeToSpendCents?.let { parts += "${formatCentsCompact(it)} safe to spend" }
    if (state.reviewCount > 0) parts += "${state.reviewCount} to review"
    state.nextBill?.let { bill -> parts += "${bill.biller} due ${formatShortDate(bill.dueDate)}" }
    return parts.joinToString("  ·  ")
}

@Composable
private fun MonthPanel(
    summary: MonthlySummaryOut,
    history: List<com.magpie.data.remote.MonthSummaryOut>,
) {
    // 6-month trend series per tile (#13). Spend uses magnitudes so the bars read "how much"
    // rather than as an inverted dip; income uses its signed value; savings rate is net/income.
    val incomeSeries = history.map { it.incomeCents.toFloat() }
    val spendSeries = history.map { kotlin.math.abs(it.spendCents.toFloat()) }
    val savingsSeries = history.map { savingsRateFraction(it.netCents, it.incomeCents) }
    PanelCard(channel = MagpieTheme.colors.money.base) {
        SectionHeader(label = "This month", channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(12.dp))
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            // Color grammar (#31): income green, savings teal (money), but spend is neutral  -  with
            // the transaction rows now neutral too, red is reserved for real deviations. Net moved to
            // the hero, so its tile is now "Savings" (how much of income you kept this month).
            MonthStatTile("Income", formatCentsCompact(summary.incomeCents),
                MagpieTheme.colors.underBudget.base, incomeSeries, Modifier.weight(1f))
            MonthStatTile("Spend", formatCentsCompact(summary.spendCents),
                MaterialTheme.colorScheme.onSurface, spendSeries, Modifier.weight(1f))
            MonthStatTile("Savings", savingsRateLabel(summary.netCents, summary.incomeCents),
                MagpieTheme.colors.money.base, savingsSeries, Modifier.weight(1f))
        }
    }
}

/** Savings rate = net / income, as a whole-percent label ("71%"); "—" when no income to divide by
 * (and never a misleading 0% when there's simply no income yet this month). */
private fun savingsRateLabel(netCents: Long, incomeCents: Long): String =
    if (incomeCents <= 0L) "—" else "${Math.round(netCents.toDouble() / incomeCents * 100.0)}%"

/** Savings rate as a fraction for the trend sparkline (0 when no income — a flat, honest baseline). */
private fun savingsRateFraction(netCents: Long, incomeCents: Long): Float =
    if (incomeCents <= 0L) 0f else (netCents.toDouble() / incomeCents).toFloat()

/**
 * Local month-panel metric tile (#30). Mirrors Pulse's dense `StatTile` (mono numerals) but pins
 * the value to a single line (`maxLines = 1, softWrap = false`) at a slightly smaller size, so a
 * money value  -  inherently longer than the siblings' "148"/"101 g"  -  fits a 1/3-width column
 * instead of wrapping mid-number.
 */
@Composable
private fun MonthStatTile(
    label: String,
    value: String,
    channel: androidx.compose.ui.graphics.Color,
    sparkline: List<Float>,
    modifier: Modifier = Modifier,
) {
    PanelCard(channel = channel, modifier = modifier, contentPadding = 14.dp) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                label.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            AutoFitValue(value = value, color = channel)
            // The 6-month trend in the slot the dense sibling tiles already carry (Spotter's usage).
            if (sparkline.size >= 2) {
                Sparkline(
                    values = sparkline,
                    channel = channel,
                    asBars = false,
                    strokeWidth = 2.dp,
                    modifier = Modifier.fillMaxWidth().height(18.dp),
                )
            }
        }
    }
}

/**
 * A stat value that shrinks to fit its column rather than truncating (#35). The #30 single-line
 * pin still holds, but at a large system font scale (a11y) a longer money value would ellipsize
 * to "-$1,3…"; here it steps the font down until it fits (floored so it stays readable), and stays
 * hidden until the fitting size is known so there's no visible reflow.
 */
@Composable
private fun AutoFitValue(
    value: String,
    color: androidx.compose.ui.graphics.Color,
    modifier: Modifier = Modifier,
) {
    var fontSize by remember(value) { mutableStateOf(16.sp) }
    var readyToDraw by remember(value) { mutableStateOf(false) }
    Text(
        value,
        style = Pulse.dataType.dataSmall.copy(fontSize = fontSize),
        color = color,
        maxLines = 1,
        softWrap = false,
        overflow = TextOverflow.Clip,
        modifier = modifier.drawWithContent { if (readyToDraw) drawContent() },
        onTextLayout = { result ->
            if (result.hasVisualOverflow && fontSize.value > 11f) {
                fontSize = (fontSize.value * 0.92f).sp
            } else {
                readyToDraw = true
            }
        },
    )
}

/**
 * The monthly-insight card (#18) in the AI voice (violet), sitting under the "This month" panel.
 * Shows the LLM "what changed" headline when one is present, otherwise a deterministic one-liner
 * about the month's biggest category move  -  so the card is useful even when the model is off.
 * It hides itself entirely when there is neither prose nor a notable change, rather than showing a
 * vacuous AI card. Tapping opens Trends, where the full breakdown lives.
 */
@Composable
private fun InsightCard(insight: MonthlyInsightOut?, onClick: () -> Unit) {
    val line = insightLine(insight) ?: return
    val channel = MagpieTheme.colors.aiVoice.base
    Spacer(Modifier.height(12.dp))
    PanelCard(channel = channel, onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column {
            SectionHeader(label = "Insight", channel = channel)
            Spacer(Modifier.height(8.dp))
            insight?.narrativeHeadline?.takeIf { insight.narrativeSource == "llm" }?.let { head ->
                Text(head, style = MaterialTheme.typography.titleSmall, color = channel)
                Spacer(Modifier.height(2.dp))
            }
            Text(line, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/** The card's body text: the LLM summary when present, else a deterministic biggest-mover line, or
 *  null when there's nothing worth surfacing (so [InsightCard] can hide). Pure, so it's unit- and
 *  screenshot-testable without a model. */
internal fun insightLine(insight: MonthlyInsightOut?): String? {
    if (insight == null) return null
    if (insight.narrativeSource == "llm" && !insight.narrativeSummary.isNullOrBlank()) {
        return insight.narrativeSummary
    }
    val mover = insight.categoryChanges.firstOrNull() ?: return null
    // Only surface a change that's both materially large and a real swing from the usual.
    if (kotlin.math.abs(mover.deltaCents) < 5_000) return null
    val direction = if (mover.deltaCents > 0) "over" else "under"
    val amount = formatCentsCompact(kotlin.math.abs(mover.deltaCents))
    return "${mover.category} is running $amount $direction its usual this month."
}

/** The "Ask Magpie" entry (#21)  -  a violet AI-voice card, so the assistant reads the same as the
 *  insight card's voice. Tappable to the chat screen. */
@Composable
private fun AskMagpieCard(onClick: () -> Unit) {
    val channel = MagpieTheme.colors.aiVoice.base
    PanelCard(channel = channel, onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column {
            SectionHeader(label = "Ask Magpie", channel = channel)
            Spacer(Modifier.height(6.dp))
            Text(
                "Ask about your spending, like 'how much on dining vs May?'",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

/** Home's review-queue content card (#29)  -  the count as a live datum, tappable to the queue. */
@Composable
private fun ReviewQueueCard(count: Int, onClick: () -> Unit) {
    val channel =
        if (count > 0) MagpieTheme.colors.needsReview.base else MagpieTheme.colors.underBudget.base
    PanelCard(channel = channel, onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column {
            SectionHeader(label = "Review queue", channel = channel)
            Spacer(Modifier.height(8.dp))
            if (count > 0) {
                Text("$count", style = Pulse.dataType.dataMedium, color = channel)
                Text("to review", style = MaterialTheme.typography.bodyMedium)
            } else {
                Text("All caught up", style = MaterialTheme.typography.bodyLarge)
            }
        }
    }
}

/** Home's next-bill content card (#29)  -  the soonest upcoming bill, tappable to the cash-flow calendar. */
@Composable
private fun UpcomingBillCard(bill: com.magpie.data.remote.UpcomingBillOut?, onClick: () -> Unit) {
    val channel = MagpieTheme.colors.money.base
    PanelCard(channel = channel, onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth()) {
            SectionHeader(label = "Upcoming", channel = channel)
            Spacer(Modifier.height(8.dp))
            if (bill != null) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column {
                        Text(bill.biller, style = MaterialTheme.typography.bodyLarge)
                        Text(
                            "due ${formatShortDate(bill.dueDate)}",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    Text(
                        formatCents(-bill.amountDueCents),
                        color = if (bill.isOverdue) MagpieTheme.colors.overBudget.base
                        else MaterialTheme.colorScheme.onSurface,
                    )
                }
            } else {
                Text("Nothing due soon", style = MaterialTheme.typography.bodyLarge)
            }
        }
    }
}

private fun formatShortDate(iso: String): String = runCatching {
    java.time.LocalDate.parse(iso)
        .format(java.time.format.DateTimeFormatter.ofPattern("MMM d"))
}.getOrDefault(iso)

@Composable
private fun CreateFirstAccountForm(
    onCreate: (name: String, institution: String, type: String, last4: String?) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var institution by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("depository") }
    var last4 by remember { mutableStateOf("") }

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
        TextField(
            value = last4,
            onValueChange = { if (it.length <= 4 && it.all(Char::isDigit)) last4 = it },
            label = { Text("Last 4 (from card  -  how alerts match)") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            singleLine = true,
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
            onClick = { onCreate(name, institution, type, last4.ifBlank { null }) },
        )
    }
}
