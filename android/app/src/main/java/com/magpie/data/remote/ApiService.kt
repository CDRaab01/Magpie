package com.magpie.data.remote

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface ApiService {

    // --- Auth (SSO-only — no register/login; see CLAUDE.md locked decisions) ---
    @POST("auth/suite")
    suspend fun suiteLogin(@Body req: SuiteLoginRequest): TokenResponse

    @POST("auth/refresh")
    suspend fun refresh(@Body req: RefreshRequest): TokenResponse

    // --- Accounts ---
    @GET("accounts")
    suspend fun listAccounts(): List<AccountOut>

    @POST("accounts")
    suspend fun createAccount(@Body req: AccountCreate): AccountOut

    @DELETE("accounts/{id}")
    suspend fun deleteAccount(@Path("id") id: String)

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

    // --- Cash-flow calendar ---
    @GET("subscriptions")
    suspend fun getSubscriptions(): SubscriptionsOut

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
}
