package com.magpie.data.repository

import com.magpie.data.local.db.CashEntryDao
import com.magpie.data.local.db.PendingCashEntryEntity
import com.magpie.data.remote.AccountCreate
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.BillOut
import com.magpie.data.remote.BudgetCreate
import com.magpie.data.remote.BudgetOut
import com.magpie.data.remote.CashflowCalendarOut
import com.magpie.data.remote.CategoryCreate
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.CategorySummaryOut
import com.magpie.data.remote.CategoryUpdate
import com.magpie.data.remote.HistoryOut
import com.magpie.data.remote.MerchantSummaryOut
import com.magpie.data.remote.SafeToSpendOut
import com.magpie.data.remote.ImportSummaryOut
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.data.remote.RefreshRequest
import com.magpie.data.remote.RuleCreate
import com.magpie.data.remote.RuleOut
import com.magpie.data.remote.RuleUpdate
import com.magpie.data.remote.SuiteLoginRequest
import com.magpie.data.remote.TokenResponse
import com.magpie.data.remote.SplitRequest
import com.magpie.data.remote.SplitResult
import com.magpie.data.remote.TransactionCreate
import com.magpie.data.remote.TransactionOut
import com.magpie.data.remote.VersionOut
import java.io.IOException
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.test.runTest
import org.junit.Test

/** In-memory DAO — the interface is small enough to fake faithfully. */
private class FakeCashEntryDao : CashEntryDao {
    val rows = mutableListOf<PendingCashEntryEntity>()
    private var nextId = 1L
    private val countFlow = MutableStateFlow(0)

    override suspend fun insert(entry: PendingCashEntryEntity): Long {
        val withId = entry.copy(id = nextId++)
        rows += withId
        countFlow.value = rows.size
        return withId.id
    }

    override suspend fun getAllPending(): List<PendingCashEntryEntity> = rows.toList()

    override fun observePendingCount(): Flow<Int> = countFlow

    override suspend fun delete(entry: PendingCashEntryEntity) {
        rows.removeAll { it.id == entry.id }
        countFlow.value = rows.size
    }
}

/** Fake server: an in-memory transaction list + an `offline` switch that throws IOException. */
private class FakeApi : ApiService {
    var offline = false
    val created = mutableListOf<TransactionCreate>()

    private fun gate() {
        if (offline) throw IOException("offline")
    }

    override suspend fun suiteLogin(req: SuiteLoginRequest): TokenResponse = error("unused")
    override suspend fun refresh(req: RefreshRequest): TokenResponse = error("unused")
    override suspend fun listAccounts(): List<AccountOut> = error("unused")
    override suspend fun createAccount(req: AccountCreate): AccountOut = error("unused")

    override suspend fun deleteAccount(id: String) = error("unused")
    override suspend fun splitTransaction(id: String, req: SplitRequest): SplitResult = error("unused")
    override suspend fun listCategories(): List<CategoryOut> = error("unused")
    override suspend fun createCategory(req: CategoryCreate): CategoryOut = error("unused")
    override suspend fun updateCategory(id: String, req: CategoryUpdate): CategoryOut = error("unused")
    override suspend fun deleteCategory(id: String) = error("unused")

    override suspend fun listTransactions(
        start: String?,
        end: String?,
        reviewState: String?,
        kind: String?,
        accountId: String?,
        query: String?,
        limit: Int?,
        offset: Int?,
    ): List<TransactionOut> {
        gate()
        return emptyList()
    }

    override suspend fun createTransaction(req: TransactionCreate): TransactionOut {
        gate()
        created += req
        return TransactionOut(
            id = UUID.randomUUID().toString(),
            accountId = req.accountId,
            amount = req.amount,
            currency = req.currency,
            date = req.date,
            status = req.status,
            merchantRaw = req.merchantRaw,
            merchantNorm = null,
            categoryId = req.categoryId,
            kind = req.kind,
            transferGroup = null,
            reviewState = "confirmed",
            source = "manual",
            createdAt = "2026-07-05T00:00:00Z",
        )
    }

    override suspend fun monthlySummary(year: Int, month: Int): MonthlySummaryOut = error("unused")

    override suspend fun updateTransaction(
        id: String,
        req: com.magpie.data.remote.TransactionUpdate,
    ): TransactionOut = error("unused")

    override suspend fun deleteTransaction(id: String) = error("unused")

    override suspend fun listBills(): List<BillOut> = error("unused")

    override suspend fun importCsv(
        accountId: okhttp3.RequestBody,
        institution: okhttp3.RequestBody,
        file: okhttp3.MultipartBody.Part,
    ): ImportSummaryOut = error("unused")

    override suspend fun listRules(): List<RuleOut> = error("unused")

    override suspend fun createRule(req: RuleCreate): RuleOut = error("unused")

    override suspend fun updateRule(id: String, req: RuleUpdate): RuleOut = error("unused")

    override suspend fun deleteRule(id: String) = error("unused")

    override suspend fun listBudgets(month: String): List<BudgetOut> = error("unused")

    override suspend fun createBudget(req: BudgetCreate): BudgetOut = error("unused")

    override suspend fun getCashflow(): CashflowCalendarOut = error("unused")

    override suspend fun getHistory(months: Int): HistoryOut = error("unused")

    override suspend fun getCategorySummary(month: String): CategorySummaryOut = error("unused")

    override suspend fun getTopMerchants(
        month: String,
        categoryId: String?,
        limit: Int?,
    ): MerchantSummaryOut = error("unused")

    override suspend fun getSafeToSpend(): SafeToSpendOut = error("unused")

    override suspend fun getVersion(): VersionOut = error("unused")
}

class TransactionRepositorySyncTest {

    private val api = FakeApi()
    private val dao = FakeCashEntryDao()
    private val repo = TransactionRepository(api, dao)

    @Test
    fun `online cash entry posts immediately and never queues`() = runTest {
        repo.addCashEntry("acct-1", -1200, "USD", "2026-07-01", "spend", "Coffee", null)

        assertEquals(1, api.created.size)
        assertEquals(0, dao.rows.size)
    }

    @Test
    fun `offline cash entry queues instead of throwing`() = runTest {
        api.offline = true

        repo.addCashEntry("acct-1", -1200, "USD", "2026-07-01", "spend", "Coffee", null)

        assertEquals(0, api.created.size)
        assertEquals(1, dao.rows.size)
        assertEquals("Coffee", dao.rows.single().merchantRaw)
    }

    @Test
    fun `syncPending drains the queue in order once back online`() = runTest {
        api.offline = true
        repo.addCashEntry("acct-1", -500, "USD", "2026-07-01", "spend", "First", null)
        repo.addCashEntry("acct-1", -700, "USD", "2026-07-02", "spend", "Second", null)
        assertEquals(2, dao.rows.size)

        api.offline = false
        repo.syncPending()

        assertEquals(0, dao.rows.size)
        assertEquals(listOf("First", "Second"), api.created.map { it.merchantRaw })
    }

    @Test
    fun `syncPending stops at the first entry that still fails, keeping the rest queued`() = runTest {
        api.offline = true
        repo.addCashEntry("acct-1", -500, "USD", "2026-07-01", "spend", "First", null)
        repo.addCashEntry("acct-1", -700, "USD", "2026-07-02", "spend", "Second", null)

        // Still offline: sync is a no-op, backlog stays intact for the next connectivity event.
        repo.syncPending()

        assertEquals(0, api.created.size)
        assertEquals(2, dao.rows.size)
    }

    @Test
    fun `a real server error is not swallowed as offline`() = runTest {
        // A non-IOException (e.g. Retrofit's HttpException for a 422) must propagate — queueing
        // it forever would hide a real bug behind a silent "offline" state.
        val brokenApi = object : ApiService by api {
            override suspend fun createTransaction(req: TransactionCreate): TransactionOut {
                throw IllegalStateException("422 sign mismatch")
            }
        }
        val brokenRepo = TransactionRepository(brokenApi, dao)

        var threw = false
        try {
            brokenRepo.addCashEntry("acct-1", 500, "USD", "2026-07-01", "spend", "Bad", null)
        } catch (e: IllegalStateException) {
            threw = true
        }
        assertTrue(threw)
        assertEquals(0, dao.rows.size)
    }
}
