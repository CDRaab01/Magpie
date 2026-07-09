package com.magpie.ui.transactions

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.SheetState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.TransactionOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader

/**
 * #26 correction surface — the row-tap actions on the Transactions screen: recategorize any row
 * (accepting the correction as confirmed), split a not-yet-split row, and delete a manual entry.
 * Deleting is restricted to `source == "manual"` — email/CSV rows are reconciliation truth and
 * shouldn't be nuked from the ledger by a tap.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransactionActionsSheet(
    txn: TransactionOut,
    categories: List<CategoryOut>,
    categoryName: String?,
    sheetState: SheetState,
    onDismiss: () -> Unit,
    onRecategorize: (categoryId: String) -> Unit,
    onSplit: () -> Unit,
    onDelete: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        TransactionActionsContent(txn, categories, categoryName, onRecategorize, onSplit, onDelete)
    }
}

/** Pure content (screenshot-testable). */
@Composable
internal fun TransactionActionsContent(
    txn: TransactionOut,
    categories: List<CategoryOut>,
    categoryName: String?,
    onRecategorize: (categoryId: String) -> Unit,
    onSplit: () -> Unit,
    onDelete: () -> Unit,
) {
    var picking by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = MagpieTheme.spacing.lg)
            .padding(bottom = MagpieTheme.spacing.lg),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SectionHeader(
            label = txn.merchantRaw ?: txn.kind.replaceFirstChar { it.uppercase() },
            channel = MagpieTheme.colors.money.base,
        )
        Text(
            listOfNotNull(txn.date, formatCents(txn.amount), categoryName ?: "Uncategorized")
                .joinToString(" · "),
            style = MaterialTheme.typography.bodyMedium,
        )

        PulseButton(
            text = "Recategorize",
            tonal = true,
            onClick = { picking = true },
            modifier = Modifier.fillMaxWidth(),
        )
        if (!txn.isSplit) {
            PulseButton(
                text = "Split across categories",
                tonal = true,
                onClick = onSplit,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (txn.source == "manual") {
            PulseButton(
                text = "Delete",
                tonal = true,
                onClick = { confirmDelete = true },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }

    if (picking) {
        AlertDialog(
            onDismissRequest = { picking = false },
            title = { Text("Choose category") },
            text = {
                Column(Modifier.heightIn(max = 320.dp).verticalScroll(rememberScrollState())) {
                    categories.sortedBy { it.name }.forEach { c ->
                        Text(
                            c.name,
                            style = MaterialTheme.typography.bodyLarge,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { picking = false; onRecategorize(c.id) }
                                .padding(vertical = 12.dp),
                        )
                    }
                }
            },
            confirmButton = {
                PulseButton(text = "Cancel", tonal = true, compact = true, onClick = { picking = false })
            },
        )
    }

    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Delete this transaction?") },
            text = { Text("This removes the manual entry from your ledger. This can't be undone.") },
            confirmButton = {
                PulseButton(
                    text = "Delete",
                    compact = true,
                    onClick = { confirmDelete = false; onDelete() },
                )
            },
            dismissButton = {
                PulseButton(
                    text = "Cancel",
                    tonal = true,
                    compact = true,
                    onClick = { confirmDelete = false },
                )
            },
        )
    }
}
