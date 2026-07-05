package com.magpie.data.local.db

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * The offline cash-entry queue — the ONE entry surface that's offline (CLAUDE.md §2/§8;
 * everything else in Magpie is online-first against the tailnet). A row here means "not yet
 * pushed to the server"; [com.magpie.util.NetworkSyncObserver] drains it on reconnect.
 */
@Entity(tableName = "pending_cash_entries")
data class PendingCashEntryEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val accountId: String,
    val amount: Long, // signed integer cents
    val currency: String,
    val date: String, // ISO-8601 (yyyy-MM-dd)
    val kind: String,
    val merchantRaw: String?,
    val categoryId: String?,
    val createdAtMs: Long,
)
