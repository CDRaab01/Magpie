package com.magpie.ui.accounts

import com.magpie.data.local.SnapshotStore
import com.magpie.data.remote.AccountCreate
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.CheckpointCreate
import com.magpie.data.remote.CheckpointOut
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

private fun account(id: String, name: String) = AccountOut(
    id = id, name = name, institution = "US Bank", type = "depository", last4 = null,
    active = true, balanceCents = 318000, balanceDeltaCents = 0,
)

private class FakeApi : ApiService by FakeApiService() {
    var failure: Exception? = null
    var accounts = listOf(account("a1", "Checking"), account("a2", "Amex"))
    var created = 0
    var checkpoints = 0
    var deleted = 0

    private fun gate() {
        failure?.let { throw it }
    }

    override suspend fun listAccounts(): List<AccountOut> {
        gate()
        return accounts
    }

    override suspend fun createAccount(req: AccountCreate): AccountOut {
        gate()
        created++
        return account("new", req.name)
    }

    override suspend fun addCheckpoint(id: String, req: CheckpointCreate): CheckpointOut {
        gate()
        checkpoints++
        return CheckpointOut(
            id = "cp1", accountId = id, statementDate = req.statementDate,
            statedBalanceCents = req.statedBalanceCents, importBatchId = null,
        )
    }

    override suspend fun deleteAccount(id: String) {
        gate()
        deleted++
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class AccountsViewModelTest {

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
        val vm = AccountsViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals(listOf("a1", "a2"), state.accounts.map { it.id })
        assertNull(state.staleAsOfMs)
        assertNull(state.error)
        assertTrue(SnapshotStore.ACCOUNTS in snapshots.saved)
    }

    @Test
    fun `network failure with a snapshot restores last-known accounts as stale`() = runTest {
        AccountsViewModel(api, snapshots) // seed the snapshot with a successful load

        api.failure = IOException("offline")
        val vm = AccountsViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals(listOf("a1", "a2"), state.accounts.map { it.id })
        assertNotNull(state.staleAsOfMs)
        assertNull(state.error)
        assertTrue(!state.loading)
    }

    @Test
    fun `network failure with no snapshot falls through to the error state`() = runTest {
        api.failure = IOException("offline")
        val vm = AccountsViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals("offline", state.error)
        assertNull(state.staleAsOfMs)
        assertTrue(state.accounts.isEmpty())
    }

    @Test
    fun `http error keeps the error behavior even when a snapshot exists`() = runTest {
        AccountsViewModel(api, snapshots) // seed the snapshot

        api.failure = HttpException(Response.error<Any>(500, "server error".toResponseBody()))
        val vm = AccountsViewModel(api, snapshots)

        val state = vm.state.value
        assertNotNull(state.error)
        assertNull(state.staleAsOfMs) // a server rejection is not an outage — no stale fallback
        assertTrue(state.accounts.isEmpty())
    }

    @Test
    fun `mutations are inert while stale`() = runTest {
        AccountsViewModel(api, snapshots)
        api.failure = IOException("offline")
        val vm = AccountsViewModel(api, snapshots)
        assertNotNull(vm.state.value.staleAsOfMs)

        api.failure = null // even with the server back, a not-yet-reloaded stale screen stays inert
        vm.createAccount("New", "US Bank", "card", null)
        vm.addCheckpoint("a1", "2026-07-15", 100000)
        vm.deleteAccount("a1")
        vm.importCsv("a1", "US Bank", byteArrayOf(1), "statement.csv")

        assertEquals(0, api.created)
        assertEquals(0, api.checkpoints)
        assertEquals(0, api.deleted)
    }

    @Test
    fun `a fresh successful reload clears staleness and re-enables mutations`() = runTest {
        AccountsViewModel(api, snapshots)
        api.failure = IOException("offline")
        val vm = AccountsViewModel(api, snapshots)
        assertNotNull(vm.state.value.staleAsOfMs)

        api.failure = null
        vm.load()

        assertNull(vm.state.value.staleAsOfMs)
        vm.createAccount("New", "US Bank", "card", null)
        assertEquals(1, api.created)
    }
}
