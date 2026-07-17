package com.magpie.testing

import com.magpie.data.local.SnapshotStore
import com.magpie.data.remote.AccountCreate
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.AddMemberRequest
import com.magpie.data.remote.ApiService
import com.magpie.data.remote.BillOut
import com.magpie.data.remote.BudgetCreate
import com.magpie.data.remote.BudgetOut
import com.magpie.data.remote.BudgetProposalOut
import com.magpie.data.remote.BudgetUpdate
import com.magpie.data.remote.CashflowCalendarOut
import com.magpie.data.remote.CategoryAnalysisOut
import com.magpie.data.remote.CategoryCreate
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.CategorySummaryOut
import com.magpie.data.remote.CategoryUpdate
import com.magpie.data.remote.ChatRequest
import com.magpie.data.remote.ChatResponse
import com.magpie.data.remote.CheckpointCreate
import com.magpie.data.remote.CheckpointOut
import com.magpie.data.remote.CoachPlanOut
import com.magpie.data.remote.CoachStatusOut
import com.magpie.data.remote.GoalOut
import com.magpie.data.remote.GoalUpsert
import com.magpie.data.remote.HistoryOut
import com.magpie.data.remote.HouseholdOut
import com.magpie.data.remote.ImportSummaryOut
import com.magpie.data.remote.InviteOut
import com.magpie.data.remote.MerchantSummaryOut
import com.magpie.data.remote.MonthlyInsightOut
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.data.remote.MuteMerchantRequest
import com.magpie.data.remote.PromotionResultOut
import com.magpie.data.remote.RefreshRequest
import com.magpie.data.remote.RuleCreate
import com.magpie.data.remote.RuleOut
import com.magpie.data.remote.RuleUpdate
import com.magpie.data.remote.SafeToSpendOut
import com.magpie.data.remote.SplitRequest
import com.magpie.data.remote.SplitResult
import com.magpie.data.remote.SubscriptionsOut
import com.magpie.data.remote.SuiteLoginRequest
import com.magpie.data.remote.TagMerchantRequest
import com.magpie.data.remote.TokenResponse
import com.magpie.data.remote.TransactionCreate
import com.magpie.data.remote.TransactionOut
import com.magpie.data.remote.TransactionUpdate
import com.magpie.data.remote.UserOut
import com.magpie.data.remote.VersionOut
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody

/**
 * A base [ApiService] where every call is `error("unused")` — ViewModel tests delegate to it
 * (`object : ApiService by FakeApiService() { … }`) and override only the endpoints their screen
 * touches, the same shape as the repository test's in-file fake.
 */
class FakeApiService : ApiService {
    override suspend fun suiteLogin(req: SuiteLoginRequest): TokenResponse = error("unused")
    override suspend fun refresh(req: RefreshRequest): TokenResponse = error("unused")
    override suspend fun getMe(): UserOut = error("unused")
    override suspend fun getHousehold(): HouseholdOut = error("unused")
    override suspend fun addHouseholdMember(req: AddMemberRequest): HouseholdOut = error("unused")
    override suspend fun removeHouseholdMember(userId: String) = error("unused")
    override suspend fun leaveHousehold() = error("unused")
    override suspend fun getHouseholdInvite(): InviteOut? = error("unused")
    override suspend fun acceptHouseholdInvite(): HouseholdOut = error("unused")
    override suspend fun declineHouseholdInvite() = error("unused")
    override suspend fun listAccounts(): List<AccountOut> = error("unused")
    override suspend fun createAccount(req: AccountCreate): AccountOut = error("unused")
    override suspend fun deleteAccount(id: String) = error("unused")
    override suspend fun listCheckpoints(id: String): List<CheckpointOut> = error("unused")
    override suspend fun addCheckpoint(id: String, req: CheckpointCreate): CheckpointOut =
        error("unused")
    override suspend fun listCategories(): List<CategoryOut> = error("unused")
    override suspend fun createCategory(req: CategoryCreate): CategoryOut = error("unused")
    override suspend fun updateCategory(id: String, req: CategoryUpdate): CategoryOut =
        error("unused")
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
    ): List<TransactionOut> = error("unused")
    override suspend fun createTransaction(req: TransactionCreate): TransactionOut = error("unused")
    override suspend fun splitTransaction(id: String, req: SplitRequest): SplitResult =
        error("unused")
    override suspend fun monthlySummary(year: Int, month: Int): MonthlySummaryOut = error("unused")
    override suspend fun updateTransaction(id: String, req: TransactionUpdate): TransactionOut =
        error("unused")
    override suspend fun deleteTransaction(id: String) = error("unused")
    override suspend fun listBills(): List<BillOut> = error("unused")
    override suspend fun importCsv(
        accountId: RequestBody,
        institution: RequestBody,
        file: MultipartBody.Part,
    ): ImportSummaryOut = error("unused")
    override suspend fun listRules(): List<RuleOut> = error("unused")
    override suspend fun createRule(req: RuleCreate): RuleOut = error("unused")
    override suspend fun updateRule(id: String, req: RuleUpdate): RuleOut = error("unused")
    override suspend fun deleteRule(id: String) = error("unused")
    override suspend fun promoteConfirmedRules(
        dryRun: Boolean,
        minTransactions: Int,
    ): PromotionResultOut = error("unused")
    override suspend fun listBudgets(month: String): List<BudgetOut> = error("unused")
    override suspend fun createBudget(req: BudgetCreate): BudgetOut = error("unused")
    override suspend fun budgetProposals(month: String): List<BudgetProposalOut> = error("unused")
    override suspend fun updateBudget(id: String, req: BudgetUpdate): BudgetOut = error("unused")
    override suspend fun coachStatus(narrative: Boolean): CoachStatusOut = error("unused")
    override suspend fun coachPlan(
        monthlySavingsCents: Long?,
        narrative: Boolean,
    ): CoachPlanOut = error("unused")
    override suspend fun coachCategory(id: String, narrative: Boolean): CategoryAnalysisOut =
        error("unused")
    override suspend fun getGoal(): GoalOut? = error("unused")
    override suspend fun setGoal(req: GoalUpsert): GoalOut = error("unused")
    override suspend fun clearGoal() = error("unused")
    override suspend fun getSubscriptions(): SubscriptionsOut = error("unused")
    override suspend fun muteSubscription(req: MuteMerchantRequest) = error("unused")
    override suspend fun tagMerchant(req: TagMerchantRequest) = error("unused")
    override suspend fun untagMerchant(req: TagMerchantRequest) = error("unused")
    override suspend fun chat(req: ChatRequest): ChatResponse = error("unused")
    override suspend fun getCashflow(): CashflowCalendarOut = error("unused")
    override suspend fun getHistory(months: Int): HistoryOut = error("unused")
    override suspend fun getCategorySummary(month: String): CategorySummaryOut = error("unused")
    override suspend fun getTopMerchants(
        month: String,
        categoryId: String?,
        limit: Int?,
    ): MerchantSummaryOut = error("unused")
    override suspend fun getSafeToSpend(): SafeToSpendOut = error("unused")
    override suspend fun getMonthlyInsight(month: String, narrative: Boolean): MonthlyInsightOut =
        error("unused")
    override suspend fun getVersion(): VersionOut = error("unused")
    override suspend fun exportTransactionsCsv(month: String): ResponseBody = error("unused")
}

/** In-memory [SnapshotStore] — what the DataStore-backed one does, minus the disk. */
class FakeSnapshotStore : SnapshotStore {
    val saved = mutableMapOf<String, String>()

    override suspend fun save(key: String, json: String) {
        saved[key] = json
    }

    override suspend fun read(key: String): String? = saved[key]
}
