package com.magpie.ui.transactions

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.SearchOff
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.SplitPart
import com.magpie.data.remote.TransactionOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.ui.util.RefreshOnResume
import com.magpie.util.formatCents
import design.pulse.ui.components.EmptyState
import design.pulse.ui.components.PanelCard

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransactionsScreen(navController: NavController) {
    val viewModel: TransactionsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }
    TransactionsContent(
        state = state,
        onSetFilter = viewModel::setFilter,
        onSetAccount = viewModel::setAccount,
        onSetQuery = viewModel::setQuery,
        onLoadMore = viewModel::loadMore,
        onRecategorize = viewModel::recategorize,
        onSplit = viewModel::split,
        onDelete = viewModel::delete,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun TransactionsContent(
    state: TransactionsUiState,
    onSetFilter: (TxnFilter) -> Unit,
    onSetAccount: (String?) -> Unit,
    onSetQuery: (String) -> Unit,
    onLoadMore: () -> Unit,
    onRecategorize: (transactionId: String, categoryId: String) -> Unit,
    onSplit: (transactionId: String, parts: List<SplitPart>) -> Unit,
    onDelete: (transactionId: String) -> Unit,
) {
    var acting by remember { mutableStateOf<TransactionOut?>(null) }
    var splitting by remember { mutableStateOf<TransactionOut?>(null) }

    Scaffold(topBar = { TopAppBar(title = { Text("Transactions") }) }) { padding ->
        when (val s = state) {
            is TransactionsUiState.Loading -> Box(
                Modifier.fillMaxSize().padding(padding), Alignment.Center,
            ) { CircularProgressIndicator() }

            is TransactionsUiState.Error -> EmptyState(
                icon = Icons.Default.Refresh,
                title = "Couldn't load",
                subtitle = s.message,
                modifier = Modifier.padding(padding),
            )

            is TransactionsUiState.Ready -> Column(Modifier.padding(padding).fillMaxSize()) {
                SearchField(query = s.query, onQuery = onSetQuery)
                if (s.accounts.size > 1) {
                    AccountFilterRow(s.accounts.map { it.id to it.name }, s.accountId, onSetAccount)
                }
                FilterRow(selected = s.filter, onSelect = onSetFilter)

                val listState = rememberLazyListState()
                val loadMore by remember(s.items.size, s.endReached) {
                    derivedStateOf {
                        val last = listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0
                        !s.endReached && !s.appending && last >= s.items.size - 5
                    }
                }
                androidx.compose.runtime.LaunchedEffect(loadMore) { if (loadMore) onLoadMore() }

                when {
                    s.items.isEmpty() && (s.query.isNotBlank() || s.accountId != null ||
                        s.filter != TxnFilter.ALL) -> EmptyState(
                        icon = Icons.Default.SearchOff,
                        title = "Nothing matches",
                        subtitle = "Try clearing the search or filters.",
                    )
                    s.items.isEmpty() -> EmptyState(
                        icon = Icons.AutoMirrored.Filled.ReceiptLong,
                        title = "No transactions yet",
                        subtitle = "Alert emails file here automatically once your accounts are set up.",
                    )
                    else -> LazyColumn(
                        state = listState,
                        modifier = Modifier.padding(horizontal = MagpieTheme.spacing.md),
                    ) {
                        items(s.items, key = { it.id }) { txn ->
                            TransactionRow(txn, s.categoryNamesById[txn.categoryId], onClick = { acting = txn })
                        }
                        if (s.appending) {
                            item {
                                Box(Modifier.fillMaxWidth().padding(16.dp), Alignment.Center) {
                                    CircularProgressIndicator()
                                }
                            }
                        }
                    }
                }

                acting?.let { txn ->
                    TransactionActionsSheet(
                        txn = txn,
                        categories = s.categories,
                        categoryName = s.categoryNamesById[txn.categoryId],
                        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
                        onDismiss = { acting = null },
                        onRecategorize = { catId -> onRecategorize(txn.id, catId); acting = null },
                        onSplit = { acting = null; splitting = txn },
                        onDelete = { onDelete(txn.id); acting = null },
                    )
                }
                splitting?.let { txn ->
                    SplitSheet(
                        txn = txn,
                        categoryNames = s.categoryNamesById,
                        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
                        onDismiss = { splitting = null },
                        onSplit = { parts -> onSplit(txn.id, parts); splitting = null },
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SearchField(query: String, onQuery: (String) -> Unit) {
    OutlinedTextField(
        value = query,
        onValueChange = onQuery,
        singleLine = true,
        leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
        placeholder = { Text("Search merchant") },
        keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(imeAction = ImeAction.Search),
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = MagpieTheme.spacing.md, vertical = 4.dp),
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AccountFilterRow(
    accounts: List<Pair<String, String>>,
    selectedId: String?,
    onSelect: (String?) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = MagpieTheme.spacing.md, vertical = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        FilterChip(
            selected = selectedId == null,
            onClick = { onSelect(null) },
            label = { Text("All accounts") },
        )
        accounts.forEach { (id, name) ->
            FilterChip(
                selected = selectedId == id,
                onClick = { onSelect(id) },
                label = { Text(name) },
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterRow(selected: TxnFilter, onSelect: (TxnFilter) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = MagpieTheme.spacing.md, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        TxnFilter.entries.forEach { filter ->
            FilterChip(
                selected = selected == filter,
                onClick = { onSelect(filter) },
                label = { Text(filter.label) },
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TransactionRow(txn: TransactionOut, categoryName: String?, onClick: () -> Unit) {
    // Color grammar (#31): ordinary spend is neutral — red is reserved for real deviations. Only
    // income gets the green channel; everything else stays neutral.
    val isIncome = txn.kind == "income"
    val accent = if (isIncome) MagpieTheme.colors.underBudget.base else null
    val amountColor =
        if (isIncome) MagpieTheme.colors.underBudget.base else MaterialTheme.colorScheme.onSurface
    PanelCard(
        channel = accent,
        onClick = onClick,
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(txn.merchantNorm ?: txn.merchantRaw ?: txn.kind.replaceFirstChar { it.uppercase() })
                Text(
                    listOfNotNull(txn.date, categoryName, if (txn.isSplit) "Split" else null)
                        .joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Text(formatCents(txn.amount), color = amountColor)
        }
    }
}
