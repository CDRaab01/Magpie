package com.magpie.ui.bills

import com.magpie.data.local.SnapshotStore
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.BillOut
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

private fun bill(id: String, biller: String) = BillOut(
    id = id, biller = biller, accountId = "acct-1", amountDue = 4500,
    dueDate = "2026-07-20", issuedAt = "2026-07-01T00:00:00Z",
    matchedTransactionId = null, isMissing = false,
)

private class FakeApi : ApiService by FakeApiService() {
    var failure: Exception? = null
    var bills = listOf(bill("b1", "XCEL ENERGY"), bill("b2", "SAMPLE INTERNET CO"))

    override suspend fun listBills(): List<BillOut> {
        failure?.let { throw it }
        return bills
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class BillsViewModelTest {

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

    @Test
    fun `success loads fresh, saves a snapshot, and is not stale`() = runTest {
        val vm = BillsViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals(listOf("b1", "b2"), state.bills.map { it.id })
        assertNull(state.staleAsOfMs)
        assertNull(state.error)
        assertTrue(SnapshotStore.BILLS in snapshots.saved)
    }

    @Test
    fun `network failure with a snapshot restores last-known bills as stale`() = runTest {
        BillsViewModel(api, snapshots) // seed the snapshot with a successful load

        api.failure = IOException("offline")
        val vm = BillsViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals(listOf("b1", "b2"), state.bills.map { it.id })
        assertNotNull(state.staleAsOfMs)
        assertNull(state.error)
        assertTrue(!state.loading)
    }

    @Test
    fun `network failure with no snapshot falls through to the error state`() = runTest {
        api.failure = IOException("offline")
        val vm = BillsViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals("offline", state.error)
        assertNull(state.staleAsOfMs)
        assertTrue(state.bills.isEmpty())
    }

    @Test
    fun `http error keeps the error behavior even when a snapshot exists`() = runTest {
        BillsViewModel(api, snapshots) // seed the snapshot

        api.failure = HttpException(Response.error<Any>(500, "server error".toResponseBody()))
        val vm = BillsViewModel(api, snapshots)

        val state = vm.state.value
        assertNotNull(state.error)
        assertNull(state.staleAsOfMs) // a server rejection is not an outage — no stale fallback
        assertTrue(state.bills.isEmpty())
    }

    @Test
    fun `a fresh successful reload clears staleness`() = runTest {
        BillsViewModel(api, snapshots)
        api.failure = IOException("offline")
        val vm = BillsViewModel(api, snapshots)
        assertNotNull(vm.state.value.staleAsOfMs)

        api.failure = null
        vm.load()

        assertNull(vm.state.value.staleAsOfMs)
        assertEquals(2, vm.state.value.bills.size)
    }
}
