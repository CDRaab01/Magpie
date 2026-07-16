package com.magpie.data.remote

import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.HTTP
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface ApiService {

    // --- Auth (SSO-only — no register/login; see CLAUDE.md locked decisions) ---
    @POST("auth/suite")
    suspend fun suiteLogin(@Body req: SuiteLoginRequest): TokenResponse

    @POST("auth/refresh")
    suspend fun refresh(@Body req: RefreshRequest): TokenResponse

    @GET("auth/me")
    suspend fun getMe(): UserOut

    // --- Household (family mode) ---
    @GET("household")
    suspend fun getHousehold(): HouseholdOut

    @POST("household/members")
    suspend fun addHouseholdMember(@Body req: AddMemberRequest): HouseholdOut

    @DELETE("household/members/{userId}")
    suspend fun removeHouseholdMember(@Path("userId") userId: String)

    @POST("household/leave")
    suspend fun leaveHousehold()

    // The invite awaiting this user's response (null body when there is none).
    @GET("household/invite")
    suspend fun getHouseholdInvite(): InviteOut?

    @POST("household/accept")
    suspend fun acceptHouseholdInvite(): HouseholdOut

    @POST("household/decline")
    suspend fun declineHouseholdInvite()

    // --- Accounts ---
    @GET("accounts")
    suspend fun listAccounts(): List<AccountOut>

    @POST("accounts")
    suspend fun createAccount(@Body req: AccountCreate): AccountOut

    @DELETE("accounts/{id}")
    suspend fun deleteAccount(@Path("id") id: String)

    @GET("accounts/{id}/checkpoints")
    suspend fun listCheckpoints(@Path("id") id: String): List<CheckpointOut>

    @POST("accounts/{id}/checkpoints")
    suspend fun addCheckpoint(
        @Path("id") id: String,
        @Body req: CheckpointCreate,
    ): CheckpointOut

    // --- Categories ---
    @GET("categories")
    suspend fun listCategories(): List<CategoryOut>

    @POST("categories")
    suspend fun createCategory(@Body req: CategoryCreate): CategoryOut

    @PATCH("categories/{id}")
    suspend fun updateCategory(
        @Path("id") id: String,
        @Body req: CategoryUpdate,
    ): CategoryOut

    @DELETE("categories/{id}")
    suspend fun deleteCategory(@Path("id") id: String)

    // --- Transactions ---
    @GET("transactions")
    suspend fun listTransactions(
        @Query("start") start: String? = null,
        @Query("end") end: String? = null,
        @Query("review_state") reviewState: String? = null,
        @Query("kind") kind: String? = null, // #32 spend/income filter
        @Query("account_id") accountId: String? = null, // #32 account filter
        @Query("q") query: String? = null, // #32 merchant search
        @Query("limit") limit: Int? = null, // #32 infinite scroll
        @Query("offset") offset: Int? = null,
    ): List<TransactionOut>

    @POST("transactions")
    suspend fun createTransaction(@Body req: TransactionCreate): TransactionOut

    @POST("transactions/{id}/split")
    suspend fun splitTransaction(@Path("id") id: String, @Body req: SplitRequest): SplitResult

    @GET("transactions/summary")
    suspend fun monthlySummary(
        @Query("year") year: Int,
        @Query("month") month: Int,
    ): MonthlySummaryOut

    @PATCH("transactions/{id}")
    suspend fun updateTransaction(
        @Path("id") id: String,
        @Body req: TransactionUpdate,
    ): TransactionOut

    @DELETE("transactions/{id}")
    suspend fun deleteTransaction(@Path("id") id: String)

    // --- Bills ---
    @GET("bills")
    suspend fun listBills(): List<BillOut>

    // --- Imports ---
    @Multipart
    @POST("imports/csv")
    suspend fun importCsv(
        @Part("account_id") accountId: RequestBody,
        @Part("institution") institution: RequestBody,
        @Part file: MultipartBody.Part,
    ): ImportSummaryOut

    // --- Rules ---
    @GET("rules")
    suspend fun listRules(): List<RuleOut>

    @POST("rules")
    suspend fun createRule(@Body req: RuleCreate): RuleOut

    @PATCH("rules/{id}")
    suspend fun updateRule(@Path("id") id: String, @Body req: RuleUpdate): RuleOut

    @DELETE("rules/{id}")
    suspend fun deleteRule(@Path("id") id: String)

    // Turn merchants you've already categorized into auto-filing rules (#25). dry_run=true just
    // previews the count; the screen previews first, then calls again with dry_run=false to apply.
    @POST("rules/from-confirmed")
    suspend fun promoteConfirmedRules(
        @Query("dry_run") dryRun: Boolean,
        @Query("min_transactions") minTransactions: Int = 2,
    ): PromotionResultOut

    // --- Budgets ---
    @GET("budgets")
    suspend fun listBudgets(@Query("month") month: String): List<BudgetOut>

    @POST("budgets")
    suspend fun createBudget(@Body req: BudgetCreate): BudgetOut

    // #17: "set budgets from your history" — trailing-median spend per category with no budget yet.
    @GET("budgets/proposals")
    suspend fun budgetProposals(@Query("month") month: String): List<BudgetProposalOut>

    // AI budget coach: accepting a coach cut draft (or a manual edit) is a budget PATCH.
    @PATCH("budgets/{id}")
    suspend fun updateBudget(@Path("id") id: String, @Body req: BudgetUpdate): BudgetOut

    // --- AI budget coach ---
    @GET("coach/status")
    suspend fun coachStatus(@Query("narrative") narrative: Boolean = false): CoachStatusOut

    @GET("coach/plan")
    suspend fun coachPlan(
        @Query("monthly_savings_cents") monthlySavingsCents: Long? = null,
        @Query("narrative") narrative: Boolean = false,
    ): CoachPlanOut

    @GET("coach/category/{id}")
    suspend fun coachCategory(
        @Path("id") id: String,
        @Query("narrative") narrative: Boolean = false,
    ): CategoryAnalysisOut

    @GET("coach/goal")
    suspend fun getGoal(): GoalOut?

    @PUT("coach/goal")
    suspend fun setGoal(@Body req: GoalUpsert): GoalOut

    @DELETE("coach/goal")
    suspend fun clearGoal()

    // --- Cash-flow calendar ---
    @GET("subscriptions")
    suspend fun getSubscriptions(): SubscriptionsOut

    // #12: mark a merchant "not a subscription" — drops it from the screen and both sweeps.
    @POST("subscriptions/mute")
    suspend fun muteSubscription(@Body req: MuteMerchantRequest)

    // Link G: tag a merchant (v1 "fitness") to show Spotter cost-per-visit; DELETE removes it.
    @POST("subscriptions/tag")
    suspend fun tagMerchant(@Body req: TagMerchantRequest)

    @HTTP(method = "DELETE", path = "subscriptions/tag", hasBody = true)
    suspend fun untagMerchant(@Body req: TagMerchantRequest)

    @POST("chat")
    suspend fun chat(@Body req: ChatRequest): ChatResponse

    @GET("cashflow")
    suspend fun getCashflow(): CashflowCalendarOut

    // --- Summary / analytics (Wave 1 read models) ---
    @GET("summary/history")
    suspend fun getHistory(@Query("months") months: Int = 6): HistoryOut

    @GET("summary/categories")
    suspend fun getCategorySummary(@Query("month") month: String): CategorySummaryOut

    @GET("summary/merchants")
    suspend fun getTopMerchants(
        @Query("month") month: String,
        @Query("category_id") categoryId: String? = null,
        @Query("limit") limit: Int? = null,
    ): MerchantSummaryOut

    @GET("summary/safe-to-spend")
    suspend fun getSafeToSpend(): SafeToSpendOut

    @GET("insights/monthly")
    suspend fun getMonthlyInsight(
        @Query("month") month: String,
        // Home uses the fast, deterministic aggregate — no LLM call blocking the screen.
        @Query("narrative") narrative: Boolean = false,
    ): MonthlyInsightOut

    // --- Ops ---
    @GET("version")
    suspend fun getVersion(): VersionOut

    // --- Export (#16) ---
    // One month's ledger as CSV. Returns the raw body (text/csv), so no JSON converter is involved;
    // `month` is any day in the month (yyyy-MM-dd), normalized server-side to the first.
    @GET("export/transactions.csv")
    suspend fun exportTransactionsCsv(@Query("month") month: String): ResponseBody
}
