package com.magpie.ui.cashentry

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.ui.theme.MagpieTheme
import design.pulse.ui.components.PulseButton

@Composable
fun CashEntryScreen(navController: NavController) {
    val viewModel: CashEntryViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(state.saved) {
        if (state.saved) navController.popBackStack()
    }

    CashEntryContent(
        state = state,
        onBack = { navController.popBackStack() },
        onSubmit = { accountId, dollars, kind, merchant, categoryId ->
            viewModel.submit(accountId, dollars, kind, merchant, categoryId)
        },
    )
}

/** Pure form (screenshot-testable): the one manual-entry surface. Holds its own field state. */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
internal fun CashEntryContent(
    state: CashEntryFormState,
    onBack: () -> Unit,
    onSubmit: (accountId: String, dollars: Double, kind: String, merchant: String, categoryId: String?) -> Unit,
) {
    var selectedAccountId by remember { mutableStateOf<String?>(null) }
    var selectedCategoryId by remember { mutableStateOf<String?>(null) }
    var kind by remember { mutableStateOf("spend") }
    var amountText by remember { mutableStateOf("") }
    var merchant by remember { mutableStateOf("") }

    LaunchedEffect(state.accounts) {
        if (selectedAccountId == null) selectedAccountId = state.accounts.firstOrNull()?.id
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Add transaction") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(MagpieTheme.spacing.lg)
                .fillMaxSize()
                .verticalScroll(rememberScrollState()),
        ) {
            Text("Kind", style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.height(4.dp))
            KindSelector(kind) { kind = it }
            Spacer(Modifier.height(16.dp))

            TextField(
                value = amountText,
                onValueChange = { amountText = it.filter { c -> c.isDigit() || c == '.' } },
                label = { Text("Amount ($)") },
                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
                    keyboardType = KeyboardType.Decimal,
                ),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(16.dp))

            if (state.accounts.size > 1) {
                Text("Account", style = MaterialTheme.typography.labelMedium)
                Spacer(Modifier.height(4.dp))
                LazyRow {
                    items(state.accounts, key = { it.id }) { account ->
                        PulseButton(
                            text = account.name,
                            tonal = selectedAccountId != account.id,
                            compact = true,
                            onClick = { selectedAccountId = account.id },
                            modifier = Modifier.padding(end = 8.dp),
                        )
                    }
                }
                Spacer(Modifier.height(16.dp))
            }

            TextField(
                value = merchant,
                onValueChange = { merchant = it },
                label = { Text("Merchant (optional)") },
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(16.dp))

            if (state.categories.isNotEmpty()) {
                Text("Category (optional)", style = MaterialTheme.typography.labelMedium)
                Spacer(Modifier.height(4.dp))
                LazyRow {
                    items(state.categories, key = { it.id }) { category ->
                        PulseButton(
                            text = category.name,
                            tonal = selectedCategoryId != category.id,
                            compact = true,
                            onClick = {
                                selectedCategoryId =
                                    if (selectedCategoryId == category.id) null else category.id
                            },
                            modifier = Modifier.padding(end = 8.dp),
                        )
                    }
                }
                Spacer(Modifier.height(16.dp))
            }

            state.error?.let {
                Text(it, color = MaterialTheme.colorScheme.error)
                Spacer(Modifier.height(8.dp))
            }

            val dollars = amountText.toDoubleOrNull()
            PulseButton(
                text = if (state.saving) "Saving…" else "Save",
                enabled = !state.saving && dollars != null && dollars > 0 && selectedAccountId != null,
                onClick = {
                    selectedAccountId?.let { accountId ->
                        onSubmit(accountId, dollars!!, kind, merchant, selectedCategoryId)
                    }
                },
            )
        }
    }
}

@Composable
private fun KindSelector(selected: String, onSelect: (String) -> Unit) {
    androidx.compose.foundation.layout.Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        CASH_ENTRY_KINDS.forEach { k ->
            PulseButton(
                text = k.replaceFirstChar { it.uppercase() },
                tonal = selected != k,
                compact = true,
                onClick = { onSelect(k) },
            )
        }
    }
}
