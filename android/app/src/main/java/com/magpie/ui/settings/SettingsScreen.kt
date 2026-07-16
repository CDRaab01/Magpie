package com.magpie.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.TextButton
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import android.content.Intent
import com.magpie.data.remote.CategoryOut
import com.magpie.ui.theme.MagpieTheme
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.ProfileHeader
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader
import java.io.File
import java.time.YearMonth

/** Thin ViewModel-wired wrapper. [SettingsContent] below is the pure, screenshot-testable half. */
@Composable
fun SettingsScreen(navController: NavController) {
    val viewModel: SettingsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current

    // #16: when an export CSV is ready, write it to cache/exports/ and hand it to the share sheet
    // via a FileProvider content:// URI. This platform glue stays out of the testable Content.
    LaunchedEffect(state.pendingExport) {
        val payload = state.pendingExport ?: return@LaunchedEffect
        try {
            val dir = File(context.cacheDir, "exports").apply { mkdirs() }
            val file = File(dir, payload.filename)
            file.writeText(payload.csv)
            val uri = FileProvider.getUriForFile(
                context, "${context.packageName}.fileprovider", file,
            )
            val send = Intent(Intent.ACTION_SEND).apply {
                type = "text/csv"
                putExtra(Intent.EXTRA_STREAM, uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            context.startActivity(
                Intent.createChooser(send, "Share ${payload.filename}")
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        } catch (_: Exception) {
            // Best-effort: a share failure must not crash Settings.
        } finally {
            viewModel.clearPendingExport()
        }
    }

    val appLockEnabled by viewModel.appLockEnabled.collectAsStateWithLifecycle()
    SettingsContent(
        state = state,
        onBack = { navController.popBackStack() },
        onAddCategory = viewModel::addCategory,
        onRenameCategory = viewModel::renameCategory,
        onDeleteCategory = viewModel::deleteCategory,
        onExportMonth = viewModel::exportMonth,
        onLogout = viewModel::logout,
        appLockEnabled = appLockEnabled,
        onSetAppLock = viewModel::setAppLock,
        onAddMember = viewModel::addHouseholdMember,
        onRemoveMember = viewModel::removeHouseholdMember,
        onLeaveHousehold = viewModel::leaveHousehold,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun SettingsContent(
    state: SettingsUiState,
    onBack: () -> Unit,
    onAddCategory: (name: String) -> Unit,
    onRenameCategory: (id: String, name: String) -> Unit,
    onDeleteCategory: (id: String) -> Unit,
    onExportMonth: (month: String) -> Unit = {},
    onLogout: () -> Unit = {},
    appLockEnabled: Boolean = false,
    onSetAppLock: (Boolean) -> Unit = {},
    onAddMember: (email: String) -> Unit = {},
    onRemoveMember: (userId: String) -> Unit = {},
    onLeaveHousehold: () -> Unit = {},
) {
    // Dialog state lives here so the whole screen stays one testable Content — a default capture
    // renders the list with every dialog closed.
    var showAddDialog by remember { mutableStateOf(false) }
    var renaming by remember { mutableStateOf<CategoryOut?>(null) }
    var deleting by remember { mutableStateOf<CategoryOut?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Settings") })
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
                else -> LazyColumn(modifier = Modifier.padding(MagpieTheme.spacing.md)) {
                    item {
                        ProfileHeader(
                            name = state.userName ?: "Signed in",
                            email = state.userEmail ?: "",
                            channel = MagpieTheme.colors.money.base,
                            channelDim = MagpieTheme.colors.money.dim,
                        )
                        Spacer(Modifier.height(24.dp))
                    }
                    item {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            SectionHeader(
                                label = "Categories",
                                channel = MagpieTheme.colors.money.base,
                            )
                            PulseButton(
                                text = "Add",
                                tonal = true,
                                compact = true,
                                onClick = { showAddDialog = true },
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                    }
                    items(state.categories, key = { it.id }) { category ->
                        CategoryRow(
                            category = category,
                            onRename = { renaming = category },
                            onDelete = { deleting = category },
                        )
                    }
                    item {
                        Spacer(Modifier.height(24.dp))
                        ExportBlock(exporting = state.exporting, onExportMonth = onExportMonth)
                    }
                    item {
                        Spacer(Modifier.height(24.dp))
                        SecurityBlock(enabled = appLockEnabled, onToggle = onSetAppLock)
                    }
                    item {
                        Spacer(Modifier.height(24.dp))
                        HouseholdBlock(
                            household = state.household,
                            error = state.householdError,
                            onAddMember = onAddMember,
                            onRemoveMember = onRemoveMember,
                            onLeave = onLeaveHousehold,
                        )
                    }
                    item {
                        Spacer(Modifier.height(24.dp))
                        AboutBlock(state.serverVersion, state.serverCommit)
                    }
                    item {
                        Spacer(Modifier.height(24.dp))
                        AccountBlock(onLogout = onLogout)
                    }
                }
            }
        }
    }

    if (showAddDialog) {
        CategoryNameDialog(
            title = "Add category",
            initial = "",
            onDismiss = { showAddDialog = false },
            onConfirm = { name ->
                onAddCategory(name)
                showAddDialog = false
            },
        )
    }

    renaming?.let { category ->
        CategoryNameDialog(
            title = "Rename category",
            initial = category.name,
            onDismiss = { renaming = null },
            onConfirm = { name ->
                onRenameCategory(category.id, name)
                renaming = null
            },
        )
    }

    deleting?.let { category ->
        AlertDialog(
            onDismissRequest = { deleting = null },
            title = { Text("Delete category") },
            text = { Text("Delete \"${category.name}\"? Transactions keep their history; this only removes the label.") },
            confirmButton = {
                PulseButton(
                    text = "Delete",
                    compact = true,
                    onClick = {
                        onDeleteCategory(category.id)
                        deleting = null
                    },
                )
            },
            dismissButton = {
                PulseButton(
                    text = "Cancel",
                    tonal = true,
                    compact = true,
                    onClick = { deleting = null },
                )
            },
        )
    }
}

@Composable
private fun CategoryRow(
    category: CategoryOut,
    onRename: () -> Unit,
    onDelete: () -> Unit,
) {
    PanelCard(
        channel = MagpieTheme.colors.money.base,
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(category.name, modifier = Modifier.weight(1f))
            if (category.shared) {
                // Seeded/shared categories are the suite vocabulary — read-only by design
                // (the server 404s a rename/delete), so no edit affordances, just a label.
                Text(
                    "Shared",
                    style = MaterialTheme.typography.labelSmall,
                    fontStyle = FontStyle.Italic,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                Row {
                    IconButton(onClick = onRename) {
                        Icon(Icons.Default.Edit, contentDescription = "Rename ${category.name}")
                    }
                    IconButton(onClick = onDelete) {
                        Icon(Icons.Default.Delete, contentDescription = "Delete ${category.name}")
                    }
                }
            }
        }
    }
}

@Composable
private fun ExportBlock(exporting: Boolean, onExportMonth: (month: String) -> Unit) {
    var month by remember { mutableStateOf(YearMonth.now().toString()) }  // "yyyy-MM"
    val valid = Regex("""\d{4}-\d{2}""").matches(month)
    PanelCard(channel = MagpieTheme.colors.money.base, modifier = Modifier.fillMaxWidth()) {
        SectionHeader(label = "Export", channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(8.dp))
        Text(
            "Download a month's transactions as a CSV and share it — your data, always yours.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(8.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextField(
                value = month,
                onValueChange = { month = it },
                label = { Text("Month (YYYY-MM)") },
                singleLine = true,
                isError = !valid,
                modifier = Modifier.weight(1f),
            )
            if (exporting) {
                CircularProgressIndicator(modifier = Modifier.height(24.dp))
            } else {
                PulseButton(
                    text = "Export",
                    enabled = valid,
                    compact = true,
                    onClick = { onExportMonth(month) },
                )
            }
        }
    }
}

@Composable
private fun SecurityBlock(enabled: Boolean, onToggle: (Boolean) -> Unit) {
    PanelCard(channel = MagpieTheme.colors.money.base, modifier = Modifier.fillMaxWidth()) {
        SectionHeader(label = "Security", channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(8.dp))
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text("Require unlock", style = MaterialTheme.typography.bodyLarge)
                Text(
                    "Ask for your fingerprint, face, or device PIN to open Magpie.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Switch(checked = enabled, onCheckedChange = onToggle)
        }
    }
}

@Composable
private fun HouseholdBlock(
    household: com.magpie.data.remote.HouseholdOut?,
    error: String?,
    onAddMember: (String) -> Unit,
    onRemoveMember: (String) -> Unit,
    onLeave: () -> Unit,
) {
    PanelCard(channel = MagpieTheme.colors.money.base, modifier = Modifier.fillMaxWidth()) {
        SectionHeader(label = "Family", channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(4.dp))
        Text(
            "Share this ledger with your household — you'll both see and manage the same accounts, " +
                "transactions, and budgets.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(12.dp))
        household?.members?.forEach { m ->
            Row(
                Modifier.fillMaxWidth().padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(m.name.ifBlank { m.email }, style = MaterialTheme.typography.bodyLarge)
                    Text(
                        if (m.isOwner) "${m.email} · owner" else m.email,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (household.youAreOwner && !m.isOwner) {
                    TextButton(onClick = { onRemoveMember(m.userId) }) { Text("Remove") }
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        if (household == null || household.youAreOwner) {
            var email by remember { mutableStateOf("") }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Share by email") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = {
                        onAddMember(email)
                        email = ""
                    },
                    enabled = email.isNotBlank(),
                ) { Text("Share") }
            }
        } else {
            TextButton(onClick = onLeave) { Text("Leave household") }
        }
        if (error != null) {
            Spacer(Modifier.height(6.dp))
            Text(
                error,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun AboutBlock(serverVersion: String?, serverCommit: String?) {
    PanelCard(channel = MagpieTheme.colors.money.base, modifier = Modifier.fillMaxWidth()) {
        SectionHeader(label = "About", channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(8.dp))
        Text("Magpie", style = MaterialTheme.typography.bodyLarge)
        Text(
            "Household cash flow — reviewed, never entered.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (serverVersion != null) {
            Spacer(Modifier.height(4.dp))
            Text(
                "Server v$serverVersion" + (serverCommit?.let { " · $it" } ?: ""),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun AccountBlock(onLogout: () -> Unit) {
    PanelCard(channel = MagpieTheme.colors.money.base, modifier = Modifier.fillMaxWidth()) {
        SectionHeader(label = "Account", channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(8.dp))
        PulseButton(
            text = "Sign out",
            tonal = true,
            compact = true,
            onClick = onLogout,
        )
    }
}

@Composable
private fun CategoryNameDialog(
    title: String,
    initial: String,
    onDismiss: () -> Unit,
    onConfirm: (name: String) -> Unit,
) {
    var name by remember { mutableStateOf(initial) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            TextField(
                value = name,
                onValueChange = { name = it },
                label = { Text("Name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        },
        confirmButton = {
            PulseButton(
                text = "Save",
                enabled = name.isNotBlank(),
                compact = true,
                onClick = { onConfirm(name) },
            )
        },
        dismissButton = {
            PulseButton(text = "Cancel", tonal = true, compact = true, onClick = onDismiss)
        },
    )
}
