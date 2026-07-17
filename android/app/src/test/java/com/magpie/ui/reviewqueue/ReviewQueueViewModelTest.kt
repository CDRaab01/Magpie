package com.magpie.ui.reviewqueue

import com.magpie.data.local.SnapshotStore
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.TransactionOut
import com.magpie.data.remote.TransactionUpdate
import com.magpie.testing.FakeApiService
import com.magpie.testing.FakeSnapshotStore
import java.io.IOException
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Before
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

private fun txn(id: String, merchant: String) = TransactionOut(
    id = id, accountId = "acct-1", amount = -1200, currency = "USD", date = "2026-07-01",
    status = "posted", merchantRaw = merchant, merchantNorm = merchant, categoryId = null,
    kind = "spend", transferGroup = null, reviewState = "needs_review", source = "email",
    createdAt = "2026-07-01T00:00:00Z",
)

/** Fake server for the queue: needs-review rows + categories, gated by a settable [failure]. */
private class FakeApi : ApiService by FakeApiService() {
    var failure: Exception? = null
    var transactions = listOf(txn("t1", "XCEL ENERGY"), txn("t2", "SAMPLE BISTRO"))
    var categories = listOf(CategoryOut("c1", "Utilities", shared = true))
    var updates = 0

    private fun gate() {
        failure?.let { throw it }
    }

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
        return transactions
    }

    override suspend fun listCategories(): List<CategoryOut> {
        gate()
        return categories
    }

    override suspend fun updateTransaction(id: String, req: TransactionUpdate): TransactionOut {
        gate()
        updates++
        return transactions.first { it.id == id }.copy(reviewState = "confirmed")
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class ReviewQueueViewModelTest {

    private val api = FakeApi()
    private val snapshots = FakeSnapshotStore()

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun offline() = IOException("offline")

    private fun http500(): HttpException =
        HttpException(Response.error<Any>(500, "server error".toResponseBody()))

    @Test
    fun `success loads fresh, saves a snapshot, and is not stale`() = runTest {
        val vm = ReviewQueueViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals(2, state.transactions.size)
        assertEquals(mapOf("c1" to "Utilities"), state.categoryNamesById)
        assertNull(state.staleAsOfMs)
        assertNull(state.error)
        assertTrue(SnapshotStore.REVIEW_QUEUE in snapshots.saved)
    }

    @Test
    fun `network failure with a snapshot restores last-known rows as stale`() = runTest {
        ReviewQueueViewModel(api, snapshots) // seed the snapshot with a successful load

        api.failure = offline()
        val vm = ReviewQueueViewModel(api, snapshots) // fresh open, server unreachable

        val state = vm.state.value
        assertEquals(listOf("t1", "t2"), state.transactions.map { it.id })
        assertEquals(mapOf("c1" to "Utilities"), state.categoryNamesById)
        assertNotNull(state.staleAsOfMs)
        assertNull(state.error)
        assertTrue(!state.loading)
    }

    @Test
    fun `network failure with no snapshot falls through to the error state`() = runTest {
        api.failure = offline()
        val vm = ReviewQueueViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals("offline", state.error)
        assertNull(state.staleAsOfMs)
        assertTrue(state.transactions.isEmpty())
    }

    @Test
    fun `http error keeps the error behavior even when a snapshot exists`() = runTest {
        ReviewQueueViewModel(api, snapshots) // seed the snapshot

        api.failure = http500()
        val vm = ReviewQueueViewModel(api, snapshots)

        val state = vm.state.value
        assertNotNull(state.error)
        assertNull(state.staleAsOfMs) // a server rejection is not an outage — no stale fallback
        assertTrue(state.transactions.isEmpty())
    }

    @Test
    fun `confirm is inert while stale`() = runTest {
        ReviewQueueViewModel(api, snapshots)
        api.failure = offline()
        val vm = ReviewQueueViewModel(api, snapshots)
        assertNotNull(vm.state.value.staleAsOfMs)

        api.failure = null // even with the server back, a not-yet-reloaded stale queue stays inert
        vm.confirm("t1")

        assertEquals(0, api.updates)
        assertEquals(2, vm.state.value.transactions.size)
    }

    @Test
    fun `a fresh successful reload clears staleness and re-enables the queue`() = runTest {
        ReviewQueueViewModel(api, snapshots)
        api.failure = offline()
        val vm = ReviewQueueViewModel(api, snapshots)
        assertNotNull(vm.state.value.staleAsOfMs)

        api.failure = null
        vm.load()

        assertNull(vm.state.value.staleAsOfMs)
        vm.confirm("t1")
        assertEquals(1, api.updates)
    }
}
