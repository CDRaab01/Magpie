package com.magpie.ui.budgets

import com.magpie.data.local.SnapshotStore
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.BudgetCreate
import com.magpie.data.remote.BudgetOut
import com.magpie.data.remote.BudgetPaceOut
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.CoachPlanOut
import com.magpie.data.remote.CoachStatusOut
import com.magpie.data.remote.GoalOut
import com.magpie.data.remote.NetProjectionOut
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

private val goal = GoalOut(
    id = "g1", kind = "monthly_savings", amountCents = 50000, createdAt = "2026-07-01T00:00:00Z",
)

private val net = NetProjectionOut(
    mtdIncomeCents = 450000, mtdSpendCents = -200000, projectedIncomeCents = 450000,
    projectedSpendCents = -400000, projectedNetCents = 50000, basis = "projection",
    goalDeltaCents = 0,
)

private fun coachStatusFixture() = CoachStatusOut(
    month = "2026-07-01",
    daysElapsed = 10,
    daysInMonth = 31,
    budgets = listOf(
        BudgetPaceOut(
            budgetId = "b1", categoryId = "c1", categoryName = "Dining", budgetCents = 20000,
            spentCents = 12000, projectedCents = 37000, remainingCents = 8000,
            dailyAllowanceCents = 380, status = "watch", trailingMedianCents = 18000,
            deltaVsUsualCents = 2000,
        ),
    ),
    goal = goal,
    net = net,
    uncategorizedMtdCents = 500,
)

private class FakeApi : ApiService by FakeApiService() {
    var failure: Exception? = null
    var budgets = listOf(
        BudgetOut(id = "b1", categoryId = "c1", month = "2026-07-01", amount = 20000, actualCents = -12000),
    )
    var categories = listOf(CategoryOut("c1", "Dining", shared = true))
    var createdBudgets = 0
    var planCalls = 0

    private fun gate() {
        failure?.let { throw it }
    }

    override suspend fun listBudgets(month: String): List<BudgetOut> {
        gate()
        return budgets
    }

    override suspend fun listCategories(): List<CategoryOut> {
        gate()
        return categories
    }

    // Best-effort extras: coach status succeeds so the restore path covers goal/net/pace rebuild;
    // budgetProposals is left unimplemented (base fake throws) — load() treats that as "none".
    override suspend fun coachStatus(narrative: Boolean): CoachStatusOut {
        gate()
        return coachStatusFixture()
    }

    override suspend fun createBudget(req: BudgetCreate): BudgetOut {
        gate()
        createdBudgets++
        return BudgetOut(
            id = "new", categoryId = req.categoryId, month = req.month, amount = req.amount,
            actualCents = 0,
        )
    }

    override suspend fun coachPlan(monthlySavingsCents: Long?, narrative: Boolean): CoachPlanOut {
        gate()
        planCalls++
        return CoachPlanOut(
            targetCents = 50000, baselineNetCents = 40000, neededCents = 10000,
            achievableCents = 10000, shortfallCents = 0, cuts = emptyList(),
        )
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class BudgetsViewModelTest {

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
        val vm = BudgetsViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals(1, state.rows.size)
        assertEquals("Dining", state.rows.single().categoryName)
        assertEquals(12000L, state.rows.single().spentCents) // -actual_cents, floored at 0
        assertEquals("watch", state.rows.single().paceStatus)
        assertEquals(goal, state.goal)
        assertNull(state.staleAsOfMs)
        assertNull(state.error)
        assertTrue(SnapshotStore.BUDGETS in snapshots.saved)
    }

    @Test
    fun `network failure with a snapshot restores rows, goal, and pace as stale`() = runTest {
        BudgetsViewModel(api, snapshots) // seed the snapshot with a successful load

        api.failure = IOException("offline")
        val vm = BudgetsViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals(1, state.rows.size)
        assertEquals("Dining", state.rows.single().categoryName)
        assertEquals("watch", state.rows.single().paceStatus) // pace rebuilt from the cached coach
        assertEquals(goal, state.goal)
        assertEquals(net, state.net)
        assertEquals(21, state.daysLeft)
        assertTrue(state.proposals.isEmpty()) // drafts are writes — never restored
        assertNotNull(state.staleAsOfMs)
        assertNull(state.error)
        assertTrue(!state.loading)
    }

    @Test
    fun `network failure with no snapshot falls through to the error state`() = runTest {
        api.failure = IOException("offline")
        val vm = BudgetsViewModel(api, snapshots)

        val state = vm.state.value
        assertEquals("offline", state.error)
        assertNull(state.staleAsOfMs)
        assertTrue(state.rows.isEmpty())
    }

    @Test
    fun `http error keeps the error behavior even when a snapshot exists`() = runTest {
        BudgetsViewModel(api, snapshots) // seed the snapshot

        api.failure = HttpException(Response.error<Any>(500, "server error".toResponseBody()))
        val vm = BudgetsViewModel(api, snapshots)

        val state = vm.state.value
        assertNotNull(state.error)
        assertNull(state.staleAsOfMs) // a server rejection is not an outage — no stale fallback
        assertTrue(state.rows.isEmpty())
    }

    @Test
    fun `mutations are inert while stale`() = runTest {
        BudgetsViewModel(api, snapshots)
        api.failure = IOException("offline")
        val vm = BudgetsViewModel(api, snapshots)
        assertNotNull(vm.state.value.staleAsOfMs)

        api.failure = null // even with the server back, a not-yet-reloaded stale screen stays inert
        vm.addBudget("c1", 30000)
        vm.acceptProposal("c1", 30000)
        vm.loadPlan()

        assertEquals(0, api.createdBudgets)
        assertEquals(0, api.planCalls)
        assertNull(vm.state.value.plan)
    }

    @Test
    fun `a fresh successful reload clears staleness and re-enables mutations`() = runTest {
        BudgetsViewModel(api, snapshots)
        api.failure = IOException("offline")
        val vm = BudgetsViewModel(api, snapshots)
        assertNotNull(vm.state.value.staleAsOfMs)

        api.failure = null
        vm.load()

        assertNull(vm.state.value.staleAsOfMs)
        vm.addBudget("c1", 30000)
        assertEquals(1, api.createdBudgets)
    }
}
