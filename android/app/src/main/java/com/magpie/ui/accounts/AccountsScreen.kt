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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
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
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.data.remote.AccountOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader

/** Thin ViewModel-wired wrapper. [AccountsContent] below is the pure, screenshot-testable half. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountsScreen(navController: NavController) {
    val viewModel: AccountsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
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
) {
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
                    state.accounts.isEmpty() -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                        Text("No accounts yet.")
                    }
                    else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                        items(state.accounts, key = { it.id }) { account ->
                            AccountRow(account, onImport = { onStartImport(account.id) })
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
}

@Composable
private fun AccountRow(account: AccountOut, onImport: () -> Unit) {
    PanelCard(channel = MagpieTheme.colors.money.base, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        SectionHeader(label = account.name, channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(8.dp))
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(account.institution, style = MaterialTheme.typography.bodySmall)
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
            }
            PulseButton(
                text = "Import CSV",
                tonal = true,
                compact = true,
                leadingIcon = { Icon(Icons.Default.UploadFile, contentDescription = null) },
                onClick = onImport,
            )
        }
    }
}
