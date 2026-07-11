package com.magpie.ui.accounts

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountBalanceWallet
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.UploadFile
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.AccountOut
import com.magpie.ui.util.RefreshOnResume
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import java.time.LocalDate
import design.pulse.ui.components.EmptyState
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader

/** Thin ViewModel-wired wrapper. [AccountsContent] below is the pure, screenshot-testable half. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountsScreen(navController: NavController) {
    val viewModel: AccountsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    RefreshOnResume { viewModel.load() }
    val context = LocalContext.current

    var pendingAccountId by remember { mutableStateOf<String?>(null) }
    var pendingUri by remember { mutableStateOf<Uri?>(null) }
    var institution by remember { mutableStateOf("") }
    var showImportDialog by remember { mutableStateOf(false) }

    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        pendingUri = uri
    }

    AccountsContent(
        state = state,
        onBack = { navController.popBackStack() },
        onStartImport = { accountId ->
            pendingAccountId = accountId
            pendingUri = null
            institution = ""
            showImportDialog = true
        },
        onDismissImportResult = viewModel::dismissImportResult,
        onAddAccount = viewModel::createAccount,
        onDelete = viewModel::deleteAccount,
        onEnterBalance = viewModel::addCheckpoint,
    )

    if (showImportDialog) {
        AlertDialog(
            onDismissRequest = { showImportDialog = false },
            title = { Text("Import CSV") },
            text = {
                Column {
                    TextField(
                        value = institution,
                        onValueChange = { institution = it },
                        label = { Text("Institution") },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Spacer(Modifier.height(12.dp))
                    PulseButton(
                        text = if (pendingUri == null) "Choose file" else "File selected",
                        tonal = pendingUri != null,
                        onClick = { filePicker.launch("text/csv") },
                    )
                }
            },
            confirmButton = {
                PulseButton(
                    text = "Import",
                    enabled = pendingUri != null && institution.isNotBlank(),
                    compact = true,
                    onClick = {
                        val uri = pendingUri
                        val accountId = pendingAccountId
                        if (uri != null && accountId != null) {
                            val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                            if (bytes != null) {
                                viewModel.importCsv(accountId, institution, bytes, "statement.csv")
                            }
                        }
                        showImportDialog = false
                    },
                )
            },
            dismissButton = {
                PulseButton(
                    text = "Cancel",
                    tonal = true,
                    compact = true,
                    onClick = { showImportDialog = false },
                )
            },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun AccountsContent(
    state: AccountsUiState,
    onBack: () -> Unit,
    onStartImport: (accountId: String) -> Unit,
    onDismissImportResult: () -> Unit,
    onAddAccount: (name: String, institution: String, type: String, last4: String?) -> Unit,
    onDelete: (accountId: String) -> Unit,
    onEnterBalance: (accountId: String, statementDate: String, statedBalanceCents: Long) -> Unit,
) {
    var showAddDialog by remember { mutableStateOf(false) }
    var deletingAccount by remember { mutableStateOf<AccountOut?>(null) }
    var enteringBalanceFor by remember { mutableStateOf<AccountOut?>(null) }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Accounts") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showAddDialog = true }) {
                Icon(Icons.Default.Add, contentDescription = "Add account")
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
            Box(modifier = Modifier.fillMaxSize()) {
                when {
                    state.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                        CircularProgressIndicator()
                    }
                    state.accounts.isEmpty() -> EmptyState(
                        icon = Icons.Default.AccountBalanceWallet,
                        title = "No accounts yet",
                        subtitle = "Tap + to add your cards and checking accounts.",
                    )
                    else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                        items(state.accounts, key = { it.id }) { account ->
                            AccountRow(
                                account,
                                onImport = { onStartImport(account.id) },
                                onDelete = { deletingAccount = account },
                                onEnterBalance = { enteringBalanceFor = account },
                            )
                        }
                    }
                }

                if (state.importing) {
                    Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
                }
            }
        }
    }

    state.importResult?.let { result ->
        AlertDialog(
            onDismissRequest = onDismissImportResult,
            title = { Text("Import complete") },
            text = {
                Text(
                    "Read ${result.rowCount} rows: ${result.createdCount} new, " +
                        "${result.skippedCount} already imported." +
                        if (result.checkpointCreated) " Balance updated." else "",
                )
            },
            confirmButton = { PulseButton(text = "OK", compact = true, onClick = onDismissImportResult) },
        )
    }

    if (showAddDialog) {
        AddAccountDialog(
            onDismiss = { showAddDialog = false },
            onConfirm = { name, institution, type, last4 ->
                onAddAccount(name, institution, type, last4)
                showAddDialog = false
            },
        )
    }

    enteringBalanceFor?.let { account ->
        EnterBalanceDialog(
            account = account,
            onDismiss = { enteringBalanceFor = null },
            onConfirm = { statementDate, statedBalanceCents ->
                onEnterBalance(account.id, statementDate, statedBalanceCents)
                enteringBalanceFor = null
            },
        )
    }

    deletingAccount?.let { account ->
        AlertDialog(
            onDismissRequest = { deletingAccount = null },
            title = { Text("Delete account?") },
            text = {
                Text("Delete “${account.name}” and all of its transactions? This can't be undone.")
            },
            confirmButton = {
                PulseButton(
                    text = "Delete",
                    compact = true,
                    onClick = {
                        onDelete(account.id)
                        deletingAccount = null
                    },
                )
            },
            dismissButton = {
                PulseButton(
                    text = "Cancel", tonal = true, compact = true,
                    onClick = { deletingAccount = null },
                )
            },
        )
    }
}

@Composable
private fun AddAccountDialog(
    onDismiss: () -> Unit,
    onConfirm: (name: String, institution: String, type: String, last4: String?) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var institution by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("card") }
    var last4 by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add account") },
        text = {
            Column {
                TextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Name (e.g. Amex)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                TextField(
                    value = institution,
                    onValueChange = { institution = it },
                    label = { Text("Institution") },
                    singleLine = true,
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
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    PulseButton("Card", tonal = type != "card", compact = true, onClick = { type = "card" })
                    PulseButton(
                        "Depository", tonal = type != "depository", compact = true,
                        onClick = { type = "depository" },
                    )
                }
            }
        },
        confirmButton = {
            PulseButton(
                text = "Add",
                enabled = name.isNotBlank() && institution.isNotBlank(),
                compact = true,
                onClick = { onConfirm(name, institution, type, last4.ifBlank { null }) },
            )
        },
        dismissButton = {
            PulseButton(text = "Cancel", tonal = true, compact = true, onClick = onDismiss)
        },
    )
}

@Composable
private fun AccountRow(
    account: AccountOut,
    onImport: () -> Unit,
    onDelete: () -> Unit,
    onEnterBalance: () -> Unit,
) {
    PanelCard(channel = MagpieTheme.colors.money.base, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        SectionHeader(label = account.name, channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(8.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    account.institution + (account.last4?.let { " · ••••$it" } ?: ""),
                    style = MaterialTheme.typography.bodySmall,
                )
                // Color grammar (#31): a normal card balance — negative for a credit card — is not an
                // alarm, so it stays neutral; the reconciled/off-by delta below carries the signal.
                Text(formatCents(account.balanceCents), color = MaterialTheme.colorScheme.onSurface)
                account.balanceDeltaCents?.let { delta ->
                    val deltaColor = if (delta == 0L) {
                        MagpieTheme.colors.underBudget.base
                    } else {
                        MagpieTheme.colors.needsReview.base
                    }
                    Text(
                        if (delta == 0L) "Reconciled" else "Off by ${formatCents(delta)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = deltaColor,
                    )
                }
                Spacer(Modifier.height(6.dp))
                // The manual statement-balance path (#4): the honesty meter only becomes real once
                // the owner has anchored a statement — this is how they do it without a CSV.
                PulseButton(
                    text = if (account.balanceDeltaCents == null) "Enter statement balance" else "Update balance",
                    tonal = true,
                    compact = true,
                    onClick = onEnterBalance,
                )
            }
            PulseButton(
                text = "Import CSV",
                tonal = true,
                compact = true,
                leadingIcon = { Icon(Icons.Default.UploadFile, contentDescription = null) },
                onClick = onImport,
            )
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Delete, contentDescription = "Delete account")
            }
        }
    }
}

@Composable
private fun EnterBalanceDialog(
    account: AccountOut,
    onDismiss: () -> Unit,
    onConfirm: (statementDate: String, statedBalanceCents: Long) -> Unit,
) {
    var statementDate by remember { mutableStateOf(LocalDate.now().toString()) }
    var amount by remember { mutableStateOf("") }
    val cents = parseDollarsToCents(amount)
    val isCard = account.type == "card"
    val dateValid = runCatching { LocalDate.parse(statementDate) }.isSuccess
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Statement balance") },
        text = {
            Column {
                Text(
                    "Enter the closing balance from ${account.name}'s statement so Magpie can " +
                        "reconcile the ledger against it.",
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(12.dp))
                TextField(
                    value = statementDate,
                    onValueChange = { statementDate = it },
                    label = { Text("Statement date (YYYY-MM-DD)") },
                    singleLine = true,
                    isError = !dateValid,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                TextField(
                    value = amount,
                    onValueChange = { amount = it },
                    label = { Text(if (isCard) "Amount owed (e.g. 840.00)" else "Balance (e.g. 2500.00)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    isError = amount.isNotBlank() && cents == null,
                    modifier = Modifier.fillMaxWidth(),
                )
                if (isCard) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "Recorded as a negative balance — what you owe.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        },
        confirmButton = {
            PulseButton(
                text = "Save",
                enabled = dateValid && cents != null,
                compact = true,
                onClick = {
                    if (cents != null) {
                        val signed = if (isCard) -kotlin.math.abs(cents) else cents
                        onConfirm(statementDate, signed)
                    }
                },
            )
        },
        dismissButton = {
            PulseButton(text = "Cancel", tonal = true, compact = true, onClick = onDismiss)
        },
    )
}

/** Parse a dollars string ("2500", "2500.00", "-84.5") to signed integer cents, or null if it
 *  isn't a clean money value. Avoids float rounding by splitting on the decimal point. */
private fun parseDollarsToCents(input: String): Long? {
    val s = input.trim().replace(",", "")
    if (s.isEmpty()) return null
    val neg = s.startsWith("-")
    val body = s.removePrefix("-").removePrefix("+")
    val parts = body.split(".")
    if (parts.size > 2) return null
    val whole = parts[0].ifEmpty { "0" }
    val frac = (parts.getOrNull(1) ?: "").padEnd(2, '0')
    if (frac.length > 2 || whole.isEmpty()) return null
    if (!whole.all(Char::isDigit) || !frac.all(Char::isDigit)) return null
    val cents = whole.toLong() * 100 + frac.toLong()
    return if (neg) -cents else cents
}
