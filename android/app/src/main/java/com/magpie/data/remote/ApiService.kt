package com.magpie.data.remote

import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
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

    // --- Categories ---
    @GET("categories")
    suspend fun listCategories(): List<CategoryOut>

    @POST("categories")
    suspend fun createCategory(@Body req: CategoryCreate): CategoryOut

    // --- Transactions ---
    @GET("transactions")
    suspend fun listTransactions(
        @Query("start") start: String? = null,
        @Query("end") end: String? = null,
    ): List<TransactionOut>

    @POST("transactions")
    suspend fun createTransaction(@Body req: TransactionCreate): TransactionOut

    @GET("transactions/summary")
    suspend fun monthlySummary(
        @Query("year") year: Int,
        @Query("month") month: Int,
    ): MonthlySummaryOut

    @DELETE("transactions/{id}")
    suspend fun deleteTransaction(@Path("id") id: String)

    // --- Ops ---
    @GET("version")
    suspend fun getVersion(): VersionOut
}
