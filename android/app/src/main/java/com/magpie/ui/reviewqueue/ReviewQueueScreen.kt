package com.magpie.ui.reviewqueue

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
import com.magpie.data.remote.TransactionOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.PulseButton

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewQueueScreen(navController: NavController) {
    val viewModel: ReviewQueueViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()

    ReviewQueueContent(
        state = state,
        onBack = { navController.popBackStack() },
        onConfirm = { id -> viewModel.confirm(id) },
        onAcceptAiSuggestion = { id, categoryId -> viewModel.confirm(id, categoryId) },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ReviewQueueContent(
    state: ReviewQueueUiState,
    onBack: () -> Unit,
    onConfirm: (transactionId: String) -> Unit,
    onAcceptAiSuggestion: (transactionId: String, categoryId: String) -> Unit,
) {
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
                state.transactions.isEmpty() -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    Text("Nothing needs review right now.")
                }
                else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                    items(state.transactions, key = { it.id }) { txn ->
                        ReviewQueueRow(
                            txn,
                            categoryNamesById = state.categoryNamesById,
                            onConfirm = { onConfirm(txn.id) },
                            onAcceptAiSuggestion = { categoryId ->
                                onAcceptAiSuggestion(txn.id, categoryId)
                            },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ReviewQueueRow(
    txn: TransactionOut,
    categoryNamesById: Map<String, String>,
    onConfirm: () -> Unit,
    onAcceptAiSuggestion: (categoryId: String) -> Unit,
) {
    val channel = when (txn.kind) {
        "income" -> MagpieTheme.colors.underBudget.base
        "spend" -> MagpieTheme.colors.overBudget.base
        "refund" -> MagpieTheme.colors.underBudget.base
        else -> MagpieTheme.colors.needsReview.base
    }
    PanelCard(
        channel = MagpieTheme.colors.needsReview.base,
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
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
            }
        }
    }
}
