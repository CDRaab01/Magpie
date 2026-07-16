package com.magpie.data.repository

import com.magpie.data.local.db.CashEntryDao
import com.magpie.data.local.db.PendingCashEntryEntity
import com.magpie.data.local.db.TransactionCacheDao
import com.magpie.data.local.db.toCacheEntity
import com.magpie.data.local.db.toTransactionOut
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.data.remote.TransactionCreate
import com.magpie.data.remote.TransactionOut
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manual cash entry is the ONE offline entry surface (CLAUDE.md §2/§8) — everything else here
 * is online-first against the tailnet. [addCashEntry] tries the server immediately; only a
 * genuine network failure (no connectivity — [IOException]) falls back to the local queue. An
 * HTTP error from a reachable server (e.g. a 422 sign-mismatch) is a real bug, not an offline
 * condition, and is left to propagate rather than queued forever.
 */
/**
 * The default (unfiltered) Transactions page: [items] plus [staleAsOfMs], which is null when the
 * page came fresh from the server and set to the cache-capture time when it was served from the
 * offline mirror (drives the "as of <time>" indicator).
 */
data class TransactionsPage(val items: List<TransactionOut>, val staleAsOfMs: Long?)

@Singleton
class TransactionRepository @Inject constructor(
    private val api: ApiService,
    private val cashEntryDao: CashEntryDao,
    private val cacheDao: TransactionCacheDao,
) {
    suspend fun addCashEntry(
        accountId: String,
        amountCents: Long,
        currency: String,
        date: String,
        kind: String,
        merchantRaw: String?,
        categoryId: String?,
    ) {
        val req = TransactionCreate(
            accountId = accountId,
            amount = amountCents,
            currency = currency,
            date = date,
            merchantRaw = merchantRaw,
            categoryId = categoryId,
            kind = kind,
        )
        try {
            api.createTransaction(req)
        } catch (e: IOException) {
            cashEntryDao.insert(
                PendingCashEntryEntity(
                    accountId = accountId,
                    amount = amountCents,
                    currency = currency,
                    date = date,
                    kind = kind,
                    merchantRaw = merchantRaw,
                    categoryId = categoryId,
                    createdAtMs = System.currentTimeMillis(),
                )
            )
        }
    }

    /** Drains the offline queue in order; stops (rather than skips) at the first entry that
     * still can't reach the server, so entries push in the order they were created. */
    suspend fun syncPending() {
        for (entry in cashEntryDao.getAllPending()) {
            try {
                api.createTransaction(
                    TransactionCreate(
                        accountId = entry.accountId,
                        amount = entry.amount,
                        currency = entry.currency,
                        date = entry.date,
                        merchantRaw = entry.merchantRaw,
                        categoryId = entry.categoryId,
                        kind = entry.kind,
                    )
                )
                cashEntryDao.delete(entry)
            } catch (e: IOException) {
                return // still offline — retry on the next connectivity event
            }
        }
    }

    suspend fun listTransactions(start: String? = null, end: String? = null): List<TransactionOut> =
        api.listTransactions(start, end)

    /**
     * The Transactions screen's opening page (unfiltered, offset 0) with an offline read-mirror:
     * a successful fetch is written through to Room and returned fresh; only a genuine network
     * failure ([IOException]) falls back to the last-known cached rows (with their capture time).
     * A reachable-server error still propagates — it's a real bug, not an offline condition. Only
     * this default view is mirrored; filtered/paginated queries stay online-only (caching arbitrary
     * filter/offset combinations would be a correctness trap, and this is the daily-review view).
     */
    suspend fun defaultFirstPage(limit: Int): TransactionsPage =
        try {
            val items = api.listTransactions(limit = limit, offset = 0)
            val now = System.currentTimeMillis()
            runCatching {
                cacheDao.replaceAll(items.mapIndexed { i, t -> t.toCacheEntity(i, now) })
            }
            TransactionsPage(items, staleAsOfMs = null)
        } catch (e: IOException) {
            val cached = cacheDao.getAll()
            if (cached.isEmpty()) throw e
            TransactionsPage(cached.map { it.toTransactionOut() }, staleAsOfMs = cached.first().cachedAtMs)
        }

    /** #32: filtered + paginated page for the Transactions screen's search / filters / scroll. */
    suspend fun listTransactionsPage(
        reviewState: String? = null,
        kind: String? = null,
        accountId: String? = null,
        query: String? = null,
        start: String? = null,
        end: String? = null,
        limit: Int,
        offset: Int,
    ): List<TransactionOut> =
        api.listTransactions(
            start = start,
            end = end,
            reviewState = reviewState,
            kind = kind,
            accountId = accountId,
            query = query?.takeIf { it.isNotBlank() },
            limit = limit,
            offset = offset,
        )

    suspend fun monthlySummary(year: Int, month: Int): MonthlySummaryOut =
        api.monthlySummary(year, month)

    suspend fun deleteTransaction(id: String) = api.deleteTransaction(id)
}
