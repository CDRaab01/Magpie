package com.magpie.data.repository

import com.magpie.data.local.db.CashEntryDao
import com.magpie.data.local.db.PendingCashEntryEntity
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
@Singleton
class TransactionRepository @Inject constructor(
    private val api: ApiService,
    private val cashEntryDao: CashEntryDao,
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

    suspend fun monthlySummary(year: Int, month: Int): MonthlySummaryOut =
        api.monthlySummary(year, month)

    suspend fun deleteTransaction(id: String) = api.deleteTransaction(id)
}
