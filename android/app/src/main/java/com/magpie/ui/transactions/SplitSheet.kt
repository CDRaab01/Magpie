package com.magpie.ui.transactions

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.SheetState
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.magpie.data.remote.SplitPart
import com.magpie.data.remote.TransactionOut
import com.magpie.ui.theme.MagpieTheme
import com.magpie.util.formatCents
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader

/** One editable allocation while splitting (before it becomes a [SplitPart]). */
private data class PartInput(val categoryId: String? = null, val amountText: String = "")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SplitSheet(
    txn: TransactionOut,
    categoryNames: Map<String, String>,
    sheetState: SheetState,
    onDismiss: () -> Unit,
    onSplit: (List<SplitPart>) -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        SplitSheetContent(txn = txn, categoryNames = categoryNames, onSplit = onSplit)
    }
}

/** Pure allocator (screenshot-testable): split [txn]'s amount across categories that must sum to it. */
@Composable
internal fun SplitSheetContent(
    txn: TransactionOut,
    categoryNames: Map<String, String>,
    onSplit: (List<SplitPart>) -> Unit,
) {
    // Parts carry the parent's sign, so the user types positive dollars and we apply it.
    val sign = if (txn.amount < 0) -1 else 1
    var parts by remember { mutableStateOf(listOf(PartInput(), PartInput())) }
    var pickingFor by remember { mutableStateOf<Int?>(null) }

    fun partCents(p: PartInput): Long =
        ((p.amountText.toDoubleOrNull() ?: 0.0) * 100).toLong() * sign
    val allocated = parts.sumOf { partCents(it) }
    val remaining = txn.amount - allocated
    val complete = remaining == 0L && parts.size >= 2 &&
        parts.all { it.categoryId != null && (it.amountText.toDoubleOrNull() ?: 0.0) > 0.0 }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = MagpieTheme.spacing.lg)
            .padding(bottom = MagpieTheme.spacing.lg),
    ) {
        SectionHeader(
            label = txn.merchantNorm ?: txn.merchantRaw ?: "Split transaction",
            channel = MagpieTheme.colors.money.base,
        )
        Text("Total ${formatCents(txn.amount)}", style = MaterialTheme.typography.bodyMedium)
        Text(
            if (remaining == 0L) "Fully allocated" else "Remaining ${formatCents(remaining)}",
            style = MaterialTheme.typography.bodySmall,
            color = if (remaining == 0L) MagpieTheme.colors.underBudget.base
            else MagpieTheme.colors.needsReview.base,
        )

        parts.forEachIndexed { index, part ->
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                PulseButton(
                    text = part.categoryId?.let { categoryNames[it] } ?: "Category",
                    tonal = true,
                    compact = true,
                    onClick = { pickingFor = index },
                )
                TextField(
                    value = part.amountText,
                    onValueChange = { v ->
                        parts = parts.toMutableList().also { it[index] = part.copy(amountText = v) }
                    },
                    label = { Text("Amount") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.weight(1f),
                )
                if (parts.size > 2) {
                    IconButton(onClick = {
                        parts = parts.toMutableList().also { it.removeAt(index) }
                    }) { Icon(Icons.Default.Close, contentDescription = "Remove part") }
                }
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            PulseButton(
                text = "Add part",
                tonal = true,
                compact = true,
                onClick = { parts = parts + PartInput() },
            )
            PulseButton(
                text = "Split",
                enabled = complete,
                onClick = {
                    onSplit(
                        parts.map {
                            SplitPart(categoryId = it.categoryId!!, amount = partCents(it), kind = txn.kind)
                        },
                    )
                },
                modifier = Modifier.weight(1f),
            )
        }
    }

    pickingFor?.let { index ->
        AlertDialog(
            onDismissRequest = { pickingFor = null },
            title = { Text("Choose category") },
            text = {
                Column(modifier = Modifier.heightIn(max = 320.dp).verticalScroll(rememberScrollState())) {
                    categoryNames.entries.sortedBy { it.value }.forEach { (id, name) ->
                        Text(
                            name,
                            style = MaterialTheme.typography.bodyLarge,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    parts = parts.toMutableList()
                                        .also { it[index] = it[index].copy(categoryId = id) }
                                    pickingFor = null
                                }
                                .padding(vertical = 12.dp),
                        )
                    }
                }
            },
            confirmButton = {
                PulseButton(text = "Cancel", tonal = true, compact = true, onClick = { pickingFor = null })
            },
        )
    }
}
