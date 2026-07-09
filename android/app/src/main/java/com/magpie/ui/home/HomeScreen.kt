package com.magpie.ui.home

import androidx.compose.material.icons.filled.Refresh
import design.pulse.ui.components.EmptyState
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
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.ui.util.RefreshOnResume
import com.magpie.ui.navigation.Routes
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import com.magpie.util.formatCentsCompact
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader
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
        onViewRules = { navController.navigate(Routes.RULES) },
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
    onViewRules: () -> Unit,
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
                MagpieHero(state)
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
                    MonthPanel(state.summary)
                    Spacer(Modifier.height(12.dp))
                    // Content, not links (#29): the review queue and the next bill are live cards
                    // showing their own data; only the two non-tab utilities (Accounts, Rules) stay
                    // as compact secondary links.
                    ReviewQueueCard(count = state.reviewCount, onClick = onViewReviewQueue)
                    Spacer(Modifier.height(8.dp))
                    UpcomingBillCard(bill = state.nextBill, onClick = onViewCashflow)
                    Spacer(Modifier.height(16.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        PulseButton(
                            text = "Accounts", tonal = true, compact = true, onClick = onViewAccounts,
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
 * The Home hero (#28) — the personalized gradient panel every sibling opens with, using the
 * indigo→teal→green "magpie" gradient that was added to Pulse for this app but until now went
 * unused. Greeting + a one-line money status ("$3,180 net this month · 3 to review · XCEL due
 * Jul 18"), the finance analogue of Plate's "TRAINED TODAY" line.
 */
@Composable
private fun MagpieHero(state: HomeUiState.Ready) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(MagpieTheme.colors.heroGradient)
            .padding(20.dp),
    ) {
        Column {
            // Sizes match Spotter's GreetingPanel — headlineMedium greeting, and a full-white
            // (not alpha'd) status line so the subtitle clears AA contrast on the hero gradient.
            Text(
                state.greeting,
                style = MaterialTheme.typography.headlineMedium,
                color = androidx.compose.ui.graphics.Color.White,
            )
            Spacer(Modifier.height(6.dp))
            Text(
                heroStatusLine(state),
                style = MaterialTheme.typography.bodyLarge,
                color = androidx.compose.ui.graphics.Color.White,
            )
        }
    }
}

private fun heroStatusLine(state: HomeUiState.Ready): String {
    val parts = mutableListOf("${formatCentsCompact(state.summary.netCents)} net this month")
    if (state.reviewCount > 0) parts += "${state.reviewCount} to review"
    state.nextBill?.let { bill -> parts += "${bill.biller} due ${formatShortDate(bill.dueDate)}" }
    return parts.joinToString("  ·  ")
}

@Composable
private fun MonthPanel(summary: MonthlySummaryOut) {
    PanelCard(channel = MagpieTheme.colors.money.base) {
        SectionHeader(label = "This month", channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(12.dp))
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            // Color grammar (#31): income green, net teal (money), but spend is neutral — with the
            // transaction rows now neutral too, red is reserved for real deviations.
            MonthStatTile("Income", formatCentsCompact(summary.incomeCents),
                MagpieTheme.colors.underBudget.base, Modifier.weight(1f))
            MonthStatTile("Spend", formatCentsCompact(summary.spendCents),
                MaterialTheme.colorScheme.onSurface, Modifier.weight(1f))
            MonthStatTile("Net", formatCentsCompact(summary.netCents),
                MagpieTheme.colors.money.base, Modifier.weight(1f))
        }
    }
}

/**
 * Local month-panel metric tile (#30). Mirrors Pulse's dense `StatTile` (mono numerals) but pins
 * the value to a single line (`maxLines = 1, softWrap = false`) at a slightly smaller size, so a
 * money value — inherently longer than the siblings' "148"/"101 g" — fits a 1/3-width column
 * instead of wrapping mid-number.
 */
@Composable
private fun MonthStatTile(
    label: String,
    value: String,
    channel: androidx.compose.ui.graphics.Color,
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
            Text(
                value,
                style = Pulse.dataType.dataSmall.copy(fontSize = 16.sp),
                color = channel,
                maxLines = 1,
                softWrap = false,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

/** Home's review-queue content card (#29) — the count as a live datum, tappable to the queue. */
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

/** Home's next-bill content card (#29) — the soonest upcoming bill, tappable to the cash-flow calendar. */
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
            label = { Text("Last 4 (from card — how alerts match)") },
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
