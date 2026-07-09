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
data class BillOut(
    val id: String,
    val biller: String,
    @SerialName("account_id") val accountId: String,
    @SerialName("amount_due") val amountDue: Long,
    @SerialName("due_date") val dueDate: String,
    @SerialName("issued_at") val issuedAt: String,
    @SerialName("matched_transaction_id") val matchedTransactionId: String?,
    @SerialName("is_missing") val isMissing: Boolean,
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
data class CategoryUpdate(
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
data class TransactionUpdate(
    @SerialName("category_id") val categoryId: String? = null,
    @SerialName("merchant_raw") val merchantRaw: String? = null,
    @SerialName("review_state") val reviewState: String? = null,
    val kind: String? = null,
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
    @SerialName("matched_rule_id") val matchedRuleId: String? = null,
    @SerialName("rule_note") val ruleNote: String? = null,
    @SerialName("ai_suggested_category_id") val aiSuggestedCategoryId: String? = null,
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

@Serializable
data class UpcomingBillOut(
    val biller: String,
    @SerialName("amount_due_cents") val amountDueCents: Long,
    @SerialName("due_date") val dueDate: String,
    @SerialName("account_name") val accountName: String,
    @SerialName("is_overdue") val isOverdue: Boolean,
    @SerialName("before_next_paycheck") val beforeNextPaycheck: Boolean,
)

@Serializable
data class CashflowCalendarOut(
    @SerialName("next_paycheck_date") val nextPaycheckDate: String?,
    @SerialName("total_due_before_paycheck_cents") val totalDueBeforePaycheckCents: Long,
    val bills: List<UpcomingBillOut>,
)

@Serializable
data class BudgetCreate(
    @SerialName("category_id") val categoryId: String,
    val month: String, // first-of-month marker, yyyy-MM-dd
    val amount: Long, // positive cents — the monthly cap
)

@Serializable
data class BudgetOut(
    val id: String,
    @SerialName("category_id") val categoryId: String,
    val month: String,
    val amount: Long,
    // Computed server-side — the actual spend/refund total for this category+month (spend is
    // negative), never stored.
    @SerialName("actual_cents") val actualCents: Long,
)

@Serializable
data class RuleCadence(
    val kind: String? = null,
    @SerialName("slack_days") val slackDays: Int? = null,
)

@Serializable
data class RuleAmountBand(
    val pct: Double? = null,
)

@Serializable
data class RuleOut(
    val id: String,
    val type: String, // recurring_income | recurring_bill | transfer_match | merchant_category
    @SerialName("account_id") val accountId: String? = null,
    val matcher: String,
    val cadence: RuleCadence? = null,
    @SerialName("amount_band") val amountBand: RuleAmountBand? = null,
    @SerialName("category_id") val categoryId: String? = null,
    @SerialName("last_matched_at") val lastMatchedAt: String? = null,
    val enabled: Boolean,
)

@Serializable
data class RuleUpdate(
    val enabled: Boolean,
)

@Serializable
data class RuleCreate(
    val type: String, // e.g. "merchant_category" for the review-queue "make this a rule" loop
    val matcher: String, // the server normalizes it (normalize_merchant)
    @SerialName("category_id") val categoryId: String,
)
