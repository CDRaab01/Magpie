package com.magpie.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class AccountCreate(
    val name: String,
    val institution: String,
    val type: String, // "card" | "depository"
    val last4: String? = null,
)

@Serializable
data class AccountOut(
    val id: String,
    val name: String,
    val institution: String,
    val type: String,
    val last4: String?,
    val active: Boolean,
    // Computed server-side (app/ledger/balances.py) — not stored.
    @SerialName("balance_cents") val balanceCents: Long,
    @SerialName("balance_delta_cents") val balanceDeltaCents: Long?,
)

@Serializable
data class ImportSummaryOut(
    @SerialName("row_count") val rowCount: Int,
    @SerialName("created_count") val createdCount: Int,
    @SerialName("matched_count") val matchedCount: Int,
    @SerialName("skipped_count") val skippedCount: Int,
    @SerialName("checkpoint_created") val checkpointCreated: Boolean,
)

@Serializable
data class CategoryCreate(
    val name: String,
)

@Serializable
data class CategoryOut(
    val id: String,
    val name: String,
    val shared: Boolean,
)

@Serializable
data class TransactionCreate(
    @SerialName("account_id") val accountId: String,
    val amount: Long, // signed integer cents — never a float
    val currency: String = "USD",
    val date: String, // ISO-8601 (yyyy-MM-dd)
    val status: String = "posted",
    @SerialName("merchant_raw") val merchantRaw: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    val kind: String, // "spend" | "income" | "transfer" | "refund"
)

@Serializable
data class TransactionOut(
    val id: String,
    @SerialName("account_id") val accountId: String,
    val amount: Long,
    val currency: String,
    val date: String,
    val status: String,
    @SerialName("merchant_raw") val merchantRaw: String?,
    @SerialName("merchant_norm") val merchantNorm: String?,
    @SerialName("category_id") val categoryId: String?,
    val kind: String,
    @SerialName("transfer_group") val transferGroup: String?,
    @SerialName("review_state") val reviewState: String,
    val source: String,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class MonthlySummaryOut(
    val year: Int,
    val month: Int,
    @SerialName("income_cents") val incomeCents: Long,
    @SerialName("spend_cents") val spendCents: Long,
    @SerialName("net_cents") val netCents: Long,
)
