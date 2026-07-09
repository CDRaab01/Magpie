package com.magpie.ui.navigation

object Routes {
    const val HOME = "home"
    const val TRANSACTIONS = "transactions"
    const val CASH_ENTRY = "cash_entry"
    const val ACCOUNTS = "accounts"
    const val REVIEW_QUEUE = "review_queue"
    const val BILLS = "bills"
    const val CASHFLOW = "cashflow"
    const val BUDGETS = "budgets"
    const val RULES = "rules"
    const val TRENDS = "trends"
    const val SETTINGS = "settings"

    // Merchant drill-down (#16) — the merchant name is URL-encoded into a single path segment.
    const val MERCHANT_DETAIL = "merchant/{merchant}"
    fun merchantDetail(merchant: String): String =
        "merchant/" + java.net.URLEncoder.encode(merchant, "UTF-8")
}
