package com.magpie.ui.reviewqueue

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SheetState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberModalBottomSheetState
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
import com.magpie.data.remote.CategoryOut
import com.magpie.ui.util.RefreshOnResume
import com.magpie.data.remote.TransactionOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.EmptyState
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewQueueScreen(navController: NavController) {
    val viewModel: ReviewQueueViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }

    ReviewQueueContent(
        state = state,
        onBack = { navController.popBackStack() },
        onConfirm = { id, categoryId, kind, ruleMatcher ->
            viewModel.confirm(id, categoryId, kind, ruleMatcher)
        },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ReviewQueueContent(
    state: ReviewQueueUiState,
    onBack: () -> Unit,
    // The one action for the whole queue: categoryId/kind are null when unchanged. Accept-as-is
    // is (id, null, null, null); accept AI or pick a category is (id, categoryId, null, null); a
    // full correction supplies the kind too. `ruleMatcher` is non-null only when the human ticked
    // "always file this merchant this way" — it creates a merchant→category rule (#22 growth loop).
    onConfirm: (
        transactionId: String,
        categoryId: String?,
        kind: String?,
        ruleMatcher: String?,
    ) -> Unit,
) {
    // Which row's correction sheet is open (null = none). Held here so [ReviewQueueContent]
    // stays the one screenshot-testable surface — the sheet is closed in a default capture.
    var correcting by remember { mutableStateOf<TransactionOut?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Review queue") },
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
            when {
                state.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    CircularProgressIndicator()
                }
                state.transactions.isEmpty() -> EmptyState(
                    icon = Icons.Default.CheckCircle,
                    title = "All caught up",
                    subtitle = "Nothing needs review right now.",
                )
                else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                    items(state.transactions, key = { it.id }) { txn ->
                        ReviewQueueRow(
                            txn,
                            categoryNamesById = state.categoryNamesById,
                            onConfirm = { onConfirm(txn.id, null, null, null) },
                            onAcceptAiSuggestion = { categoryId ->
                                onConfirm(txn.id, categoryId, null, null)
                            },
                            onCorrect = { correcting = txn },
                        )
                    }
                }
            }
        }
    }

    correcting?.let { txn ->
        CorrectionSheet(
            txn = txn,
            categories = state.categories,
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            onDismiss = { correcting = null },
            onConfirm = { categoryId, kind, ruleMatcher ->
                onConfirm(txn.id, categoryId, kind, ruleMatcher)
                correcting = null
            },
        )
    }
}

@Composable
private fun ReviewQueueRow(
    txn: TransactionOut,
    categoryNamesById: Map<String, String>,
    onConfirm: () -> Unit,
    onAcceptAiSuggestion: (categoryId: String) -> Unit,
    onCorrect: () -> Unit,
) {
    // Color grammar (#31): the row amount is neutral (only income green) — the card's amber
    // needs-review context is the one channel that matters here; red is not for ordinary spend.
    val channel = when (txn.kind) {
        "income" -> MagpieTheme.colors.underBudget.base
        else -> MaterialTheme.colorScheme.onSurface
    }
    PanelCard(
        channel = MagpieTheme.colors.needsReview.base,
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(modifier = Modifier.weight(1f)) {
                Text(txn.merchantRaw ?: txn.kind.replaceFirstChar { it.uppercase() })
                Text(txn.date, style = MaterialTheme.typography.bodySmall)
                // Distinct from a rule hit (`rule_note`, teal/needs-review text): an AI draft
                // is never shown as fact, always labeled "AI suggests" with its own accept
                // action — CLAUDE.md §6, nothing the model produces is confirmed for you.
                txn.ruleNote?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MagpieTheme.colors.needsReview.base,
                    )
                }
                txn.aiSuggestedCategoryId?.let { categoryId ->
                    val categoryName = categoryNamesById[categoryId] ?: "a category"
                    Text(
                        "AI suggests: $categoryName",
                        style = MaterialTheme.typography.bodySmall,
                        color = MagpieTheme.colors.money.base,
                    )
                }
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(formatCents(txn.amount), color = channel)
                Spacer(Modifier.height(4.dp))
                if (txn.aiSuggestedCategoryId != null) {
                    PulseButton(
                        text = "Accept AI suggestion",
                        tonal = true,
                        compact = true,
                        onClick = { onAcceptAiSuggestion(txn.aiSuggestedCategoryId) },
                    )
                } else {
                    PulseButton(text = "Confirm", tonal = true, compact = true, onClick = onConfirm)
                }
                Spacer(Modifier.height(4.dp))
                // The "correct" half of approve/correct: one extra tap opens the picker, so the
                // happy path stays one tap and a correction is at most two (open → tap category).
                // Tonal (like Confirm) keeps the list calm — a per-row solid button would be the
                // channel-density noise the Tier 4 UI pass is meant to avoid.
                PulseButton(text = "Correct", tonal = true, compact = true, onClick = onCorrect)
            }
        }
    }
}

/**
 * The correction picker: pick a category (the common case) and, for the rare sign-ambiguous
 * transaction, correct the kind too. Tapping a category confirms immediately (the two-tap
 * correction); the kind chips only change what a subsequent tap sends. "Confirm" at the bottom
 * covers a kind-only fix with no category change.
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun CorrectionSheet(
    txn: TransactionOut,
    categories: List<CategoryOut>,
    sheetState: SheetState,
    onDismiss: () -> Unit,
    onConfirm: (categoryId: String?, kind: String?, ruleMatcher: String?) -> Unit,
) {
    var selectedKind by remember { mutableStateOf(txn.kind) }
    // Only send a kind when the human actually changed it — an unchanged kind stays null so the
    // server leaves it (and its sign re-validation) untouched.
    val kindOrNull = selectedKind.takeIf { it != txn.kind }
    // The "make this a rule" growth loop (#22): tick it, then pick a category, and future
    // transactions from this merchant auto-file. Only offered when there's a merchant to match on.
    val matcher = txn.merchantRaw ?: txn.merchantNorm
    var makeRule by remember { mutableStateOf(false) }
    val ruleMatcher = matcher.takeIf { makeRule }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = MagpieTheme.spacing.lg)
                .padding(bottom = MagpieTheme.spacing.lg),
        ) {
            SectionHeader(
                label = txn.merchantRaw ?: "Transaction",
                channel = MagpieTheme.colors.needsReview.base,
            )
            Text(formatCents(txn.amount), style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(MagpieTheme.spacing.md))

            Text("Kind", style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.height(4.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("spend", "income", "refund", "transfer").forEach { kind ->
                    PulseButton(
                        text = kind.replaceFirstChar { it.uppercase() },
                        tonal = selectedKind != kind,
                        compact = true,
                        onClick = { selectedKind = kind },
                    )
                }
            }
            Spacer(Modifier.height(MagpieTheme.spacing.md))

            if (matcher != null) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { makeRule = !makeRule }
                        .padding(vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(checked = makeRule, onCheckedChange = { makeRule = it })
                    Text("Always file “$matcher” this way")
                }
                Spacer(Modifier.height(MagpieTheme.spacing.sm))
            }

            Text("Category", style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.height(4.dp))
            LazyColumn(modifier = Modifier.heightIn(max = 320.dp)) {
                items(categories, key = { it.id }) { category ->
                    Text(
                        category.name,
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onConfirm(category.id, kindOrNull, ruleMatcher) }
                            .padding(vertical = 12.dp),
                    )
                }
            }
            Spacer(Modifier.height(MagpieTheme.spacing.md))
            PulseButton(
                text = "Confirm",
                onClick = { onConfirm(null, kindOrNull, null) },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
