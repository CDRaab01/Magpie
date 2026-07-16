package com.magpie.data.local.db

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.magpie.data.remote.TransactionOut

/**
 * A read-only mirror of the default (unfiltered) Transactions page, so the ledger opens to
 * stale-but-real rows off the tailnet instead of an error state — the offline half of the
 * 10-second daily review (CLAUDE.md §3 "Offline: read cache + offline cash-entry queue"). This is
 * a pure cache: it is refreshed wholesale on every successful load and never written back to the
 * server, so a destructive migration on a schema bump only drops a cache the next online load
 * rebuilds. [position] preserves the server's order; [cachedAtMs] stamps the capture for the
 * "as of <time>" indicator.
 *
 * Nothing here is more sensitive than what the authenticated API already returns; the device-level
 * app lock (see [com.magpie.security.AppLock]) is the at-rest protection, so no separate encryption.
 */
@Entity(tableName = "cached_transactions")
data class CachedTransactionEntity(
    @PrimaryKey val id: String,
    val position: Int,
    val cachedAtMs: Long,
    val accountId: String,
    val amount: Long,
    val currency: String,
    val date: String,
    val status: String,
    val merchantRaw: String?,
    val merchantNorm: String?,
    val categoryId: String?,
    val kind: String,
    val transferGroup: String?,
    val reviewState: String,
    val source: String,
    val matchedRuleId: String?,
    val ruleNote: String?,
    val aiSuggestedCategoryId: String?,
    val isSplit: Boolean,
    val createdAt: String,
)

fun TransactionOut.toCacheEntity(position: Int, cachedAtMs: Long): CachedTransactionEntity =
    CachedTransactionEntity(
        id = id,
        position = position,
        cachedAtMs = cachedAtMs,
        accountId = accountId,
        amount = amount,
        currency = currency,
        date = date,
        status = status,
        merchantRaw = merchantRaw,
        merchantNorm = merchantNorm,
        categoryId = categoryId,
        kind = kind,
        transferGroup = transferGroup,
        reviewState = reviewState,
        source = source,
        matchedRuleId = matchedRuleId,
        ruleNote = ruleNote,
        aiSuggestedCategoryId = aiSuggestedCategoryId,
        isSplit = isSplit,
        createdAt = createdAt,
    )

fun CachedTransactionEntity.toTransactionOut(): TransactionOut =
    TransactionOut(
        id = id,
        accountId = accountId,
        amount = amount,
        currency = currency,
        date = date,
        status = status,
        merchantRaw = merchantRaw,
        merchantNorm = merchantNorm,
        categoryId = categoryId,
        kind = kind,
        transferGroup = transferGroup,
        reviewState = reviewState,
        source = source,
        matchedRuleId = matchedRuleId,
        ruleNote = ruleNote,
        aiSuggestedCategoryId = aiSuggestedCategoryId,
        isSplit = isSplit,
        createdAt = createdAt,
    )
