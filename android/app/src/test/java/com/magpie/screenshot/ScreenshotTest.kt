package com.magpie.screenshot

import android.app.Application
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import com.github.takahirom.roborazzi.ExperimentalRoborazziApi
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import com.magpie.data.remote.AccountOut
import com.magpie.data.remote.CategoryOut
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.ui.flow.CashFlowContent
import com.magpie.ui.flow.CashFlowItem
import com.magpie.data.remote.BudgetVerdictOut
import com.magpie.ui.flow.FlowKind
import com.magpie.ui.insight.InsightContent
import com.magpie.data.remote.TransactionOut
import com.magpie.data.remote.BillOut
import com.magpie.data.remote.CashflowCalendarOut
import com.magpie.data.remote.UpcomingBillOut
import com.magpie.ui.accounts.AccountsContent
import com.magpie.ui.accounts.AccountsUiState
import com.magpie.ui.bills.BillsContent
import com.magpie.ui.bills.BillsUiState
import com.magpie.data.remote.GoalOut
import com.magpie.data.remote.NetProjectionOut
import com.magpie.ui.budgets.BudgetRow
import com.magpie.ui.budgets.BudgetsContent
import com.magpie.ui.budgets.BudgetsUiState
import com.magpie.ui.cashentry.CashEntryContent
import com.magpie.ui.cashentry.CashEntryFormState
import com.magpie.ui.cashflow.CashflowContent
import com.magpie.ui.cashflow.CashflowUiState
import com.magpie.ui.signin.SignInContent
import com.magpie.ui.navigation.MagpieBottomBar
import com.magpie.ui.navigation.Routes
import com.magpie.ui.transactions.SplitSheetContent
import com.magpie.ui.transactions.TransactionsContent
import com.magpie.ui.transactions.TransactionsUiState
import com.magpie.ui.transactions.TxnFilter
import com.magpie.data.remote.CategorySummaryItem
import com.magpie.data.remote.MerchantSummaryItem
import com.magpie.data.remote.MonthSummaryOut
import com.magpie.data.remote.MonthlyInsightOut
import com.magpie.data.remote.CategoryChangeOut
import com.magpie.ui.trends.TrendsContent
import com.magpie.ui.trends.TrendsUiState
import com.magpie.ui.merchant.MerchantDetailContent
import com.magpie.ui.merchant.MerchantDetailUiState
import com.magpie.ui.rules.RuleRow
import com.magpie.ui.rules.RulesContent
import com.magpie.ui.rules.RulesUiState
import com.magpie.ui.subscriptions.SubscriptionsContent
import com.magpie.ui.subscriptions.SubscriptionsUiState
import com.magpie.data.remote.SubscriptionOut
import com.magpie.data.remote.ChatMessage
import com.magpie.ui.chat.ChatContent
import com.magpie.ui.chat.ChatUiState
import com.magpie.ui.home.HomeContent
import com.magpie.ui.home.HomeUiState
import com.magpie.ui.onboarding.OnboardingContent
import com.magpie.ui.reviewqueue.ReviewQueueContent
import com.magpie.ui.reviewqueue.ReviewQueueUiState
import com.magpie.ui.settings.SettingsContent
import com.magpie.ui.settings.SettingsUiState
import com.magpie.ui.theme.MagpieTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * JVM screenshot tests (Robolectric native graphics + Roborazzi) , render Magpie's first real
 * screen to PNGs without a device or emulator. Run with `:app:testDebugUnitTest`; images land
 * in `app/screenshots/`. Record with `-Proborazzi.test.record=true`. Mirrors the suite reference
 * (Plate/Cookbook's `ScreenshotTest`) , screenshot the pure Content composable, not the
 * ViewModel-wired screen, so no Hilt DI is needed here.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(application = Application::class, sdk = [34], qualifiers = RobolectricDeviceQualifiers.Pixel5)
class ScreenshotTest {

    @get:Rule val compose = createComposeRule()

    // A small tolerance so sub-pixel AA / font-hinting noise across machines doesn't flag a diff.
    private val roborazziOptions = RoborazziOptions(
        compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.03f),
    )

    @OptIn(ExperimentalRoborazziApi::class)
    private fun capture(name: String, dark: Boolean, content: @Composable () -> Unit) {
        compose.setContent {
            MagpieTheme(darkTheme = dark) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) { content() }
            }
        }
        compose.onRoot().captureRoboImage("screenshots/$name.png", roborazziOptions = roborazziOptions)
    }

    @Test
    fun home_ready_light() = capture("home_ready_light", dark = false) { HomeReadyScene() }

    @Test
    fun home_ready_dark() = capture("home_ready_dark", dark = true) { HomeReadyScene() }

    @Test
    fun home_needs_account_light() = capture("home_needs_account_light", dark = false) { HomeNeedsAccountScene() }

    @Test
    fun home_needs_account_dark() = capture("home_needs_account_dark", dark = true) { HomeNeedsAccountScene() }

    @Test
    fun accounts_light() = capture("accounts_light", dark = false) { AccountsScene() }

    @Test
    fun accounts_dark() = capture("accounts_dark", dark = true) { AccountsScene() }

    @Test
    fun review_queue_light() = capture("review_queue_light", dark = false) { ReviewQueueScene() }

    @Test
    fun review_queue_dark() = capture("review_queue_dark", dark = true) { ReviewQueueScene() }

    @Test
    fun bills_light() = capture("bills_light", dark = false) { BillsScene() }

    @Test
    fun bills_dark() = capture("bills_dark", dark = true) { BillsScene() }

    @Test
    fun settings_light() = capture("settings_light", dark = false) { SettingsScene() }

    @Test
    fun settings_dark() = capture("settings_dark", dark = true) { SettingsScene() }

    @Test
    fun cashflow_light() = capture("cashflow_light", dark = false) { CashflowScene() }

    @Test
    fun cashflow_dark() = capture("cashflow_dark", dark = true) { CashflowScene() }

    @Test
    fun budgets_light() = capture("budgets_light", dark = false) { BudgetsScene() }

    @Test
    fun budgets_dark() = capture("budgets_dark", dark = true) { BudgetsScene() }

    @Test
    fun rules_light() = capture("rules_light", dark = false) { RulesScene() }

    @Test
    fun rules_dark() = capture("rules_dark", dark = true) { RulesScene() }

    @Test
    fun cash_flow_light() = capture("cash_flow_light", dark = false) { CashFlowSankeyScene() }

    @Test
    fun cash_flow_dark() = capture("cash_flow_dark", dark = true) { CashFlowSankeyScene() }

    @Test
    fun insight_light() = capture("insight_light", dark = false) { InsightScene() }

    @Test
    fun insight_dark() = capture("insight_dark", dark = true) { InsightScene() }

    @org.junit.Test
    fun subscriptions_light() = capture("subscriptions_light", dark = false) { SubscriptionsScene() }

    @org.junit.Test
    fun subscriptions_dark() = capture("subscriptions_dark", dark = true) { SubscriptionsScene() }

    @org.junit.Test
    fun chat_light() = capture("chat_light", dark = false) { ChatScene() }

    @org.junit.Test
    fun chat_dark() = capture("chat_dark", dark = true) { ChatScene() }

    @Test
    fun bottom_bar_light() = capture("bottom_bar_light", dark = false) { BottomBarScene() }

    @Test
    fun bottom_bar_dark() = capture("bottom_bar_dark", dark = true) { BottomBarScene() }

    @Test
    fun transactions_light() = capture("transactions_light", dark = false) { TransactionsScene() }

    @Test
    fun transactions_dark() = capture("transactions_dark", dark = true) { TransactionsScene() }

    @Test
    fun transactions_empty_light() = capture("transactions_empty_light", dark = false) {
        TxnScene(
            TransactionsUiState.Ready(
                items = emptyList(), categoryNamesById = emptyMap(), accounts = emptyList(),
                categories = emptyList(), filter = TxnFilter.ALL, accountId = null, query = "",
                endReached = true,
            ),
        )
    }

    @Test
    fun transactions_empty_dark() = capture("transactions_empty_dark", dark = true) {
        TxnScene(
            TransactionsUiState.Ready(
                items = emptyList(), categoryNamesById = emptyMap(), accounts = emptyList(),
                categories = emptyList(), filter = TxnFilter.ALL, accountId = null, query = "",
                endReached = true,
            ),
        )
    }

    @Test
    fun onboarding_welcome_light() = capture("onboarding_welcome_light", dark = false) {
        OnboardingContent(0, false, null, {}, { _, _, _, _ -> }, {}, {}, {})
    }

    @Test
    fun onboarding_welcome_dark() = capture("onboarding_welcome_dark", dark = true) {
        OnboardingContent(0, false, null, {}, { _, _, _, _ -> }, {}, {}, {})
    }

    @Test
    fun onboarding_account_light() = capture("onboarding_account_light", dark = false) {
        OnboardingContent(1, false, null, {}, { _, _, _, _ -> }, {}, {}, {})
    }

    // #35 a11y guard: the money-dense Home at font scale 1.3 must not truncate.
    @Test
    fun home_large_font_light() = capture("home_large_font_light", dark = false) {
        androidx.compose.runtime.CompositionLocalProvider(
            androidx.compose.ui.platform.LocalDensity provides androidx.compose.ui.unit.Density(
                density = androidx.compose.ui.platform.LocalDensity.current.density,
                fontScale = 1.3f,
            ),
        ) { HomeReadyScene() }
    }

    @Test
    fun split_sheet_light() = capture("split_sheet_light", dark = false) { SplitSheetScene() }

    @Test
    fun split_sheet_dark() = capture("split_sheet_dark", dark = true) { SplitSheetScene() }

    @Test
    fun sign_in_light() = capture("sign_in_light", dark = false) { SignInScene() }

    @Test
    fun sign_in_dark() = capture("sign_in_dark", dark = true) { SignInScene() }

    @Test
    fun cash_entry_light() = capture("cash_entry_light", dark = false) { CashEntryScene() }

    @Test
    fun cash_entry_dark() = capture("cash_entry_dark", dark = true) { CashEntryScene() }

    @Test
    fun trends_light() = capture("trends_light", dark = false) { TrendsScene() }

    @Test
    fun trends_dark() = capture("trends_dark", dark = true) { TrendsScene() }

    @Test
    fun merchant_detail_light() = capture("merchant_detail_light", dark = false) { MerchantDetailScene() }

    @Test
    fun merchant_detail_dark() = capture("merchant_detail_dark", dark = true) { MerchantDetailScene() }
}

@Composable
private fun MerchantDetailScene() {
    fun txn(id: String, amount: Long, date: String) = TransactionOut(
        id = id, accountId = "a", amount = amount, currency = "USD", date = date,
        status = "posted", merchantRaw = "MEIJER", merchantNorm = "MEIJER", categoryId = "cat-groc",
        kind = "spend", transferGroup = null, reviewState = "confirmed", source = "csv",
        matchedRuleId = null, ruleNote = null, aiSuggestedCategoryId = null,
        createdAt = "2026-07-15T00:00:00Z",
    )
    MerchantDetailContent(
        state = MerchantDetailUiState(
            merchant = "MEIJER",
            transactions = listOf(
                txn("1", -8200, "2026-07-14"),
                txn("2", -9100, "2026-07-08"),
                txn("3", -7600, "2026-07-02"),
                txn("4", -7100, "2026-06-26"),
            ),
            totalCents = -32000,
            count = 4,
            averageCents = -8000,
            loading = false,
        ),
        onBack = {},
    )
}

@Composable
private fun CashFlowSankeyScene() {
    CashFlowContent(
        monthLabel = "July 2026",
        incomeCents = 450000,
        items = listOf(
            CashFlowItem("Housing", 145000, FlowKind.CATEGORY),
            CashFlowItem("Groceries", 62000, FlowKind.CATEGORY),
            CashFlowItem("Dining", 41000, FlowKind.CATEGORY),
            CashFlowItem("Transport", 24000, FlowKind.CATEGORY),
            CashFlowItem("Utilities", 18000, FlowKind.CATEGORY),
            CashFlowItem("Subscriptions", 12000, FlowKind.CATEGORY),
            CashFlowItem("Other", 16000, FlowKind.CATEGORY),
            CashFlowItem("Saved", 132000, FlowKind.SAVINGS),
        ),
    )
}

@Composable
private fun InsightScene() {
    InsightContent(
        monthLabel = "July 2026",
        insight = MonthlyInsightOut(
            month = "2026-07",
            incomeCents = 450000,
            spendCents = 318000,
            netCents = 132000,
            categoryChanges = listOf(
                CategoryChangeOut("Dining", thisMonthCents = 41000, trailingMedianCents = 28000, deltaCents = 13000),
                CategoryChangeOut("Transport", thisMonthCents = 22000, trailingMedianCents = 15000, deltaCents = 7000),
                CategoryChangeOut("Groceries", thisMonthCents = 52000, trailingMedianCents = 60000, deltaCents = -8000),
            ),
            budgetVerdicts = listOf(
                BudgetVerdictOut("Dining", actualCents = 41000, budgetCents = 35000, overCents = 6000),
                BudgetVerdictOut("Groceries", actualCents = 52000, budgetCents = 60000, overCents = 0),
            ),
            narrativeHeadline = "A solid month — you saved $1,320.",
            narrativeSummary = "Spending held near your usual, with dining running a little hot. " +
                "You cleared your grocery budget with room to spare.",
            narrativeSource = "llm",
        ),
    )
}

@Composable
private fun TrendsScene() {
    fun month(m: Int, income: Long, spend: Long) =
        MonthSummaryOut(year = 2026, month = m, incomeCents = income, spendCents = spend, netCents = income + spend)
    TrendsContent(
        state = TrendsUiState(
            monthLabel = "July 2026",
            history = listOf(
                month(2, 450000, -410000),
                month(3, 450000, -382000),
                month(4, 460000, -455000),
                month(5, 450000, -390000),
                month(6, 470000, -402000),
                month(7, 450000, -132000),
            ),
            categories = listOf(
                CategorySummaryItem("cat-groc", "Groceries", -62000),
                CategorySummaryItem("cat-dining", "Dining", -41000),
                CategorySummaryItem("cat-transport", "Transport", -18000),
                CategorySummaryItem(null, "Uncategorized", -9000),
            ),
            merchants = listOf(
                MerchantSummaryItem("MEIJER", -32000, 4),
                MerchantSummaryItem("SAMPLE BISTRO", -18000, 3),
                MerchantSummaryItem("BIG BOX", -14000, 1),
            ),
            loading = false,
        ),
        onBack = {},
    )
}

@Composable
private fun SignInScene() {
    SignInContent(error = null, onSignIn = {})
}

@Composable
private fun CashEntryScene() {
    CashEntryContent(
        state = CashEntryFormState(
            accounts = listOf(
                AccountOut(
                    id = "1", name = "Checking", institution = "US Bank", type = "depository",
                    last4 = null, active = true, balanceCents = 318000, balanceDeltaCents = 0,
                ),
                AccountOut(
                    id = "2", name = "Amex", institution = "American Express", type = "card",
                    last4 = "1234", active = true, balanceCents = -132000, balanceDeltaCents = null,
                ),
            ),
            categories = listOf(
                CategoryOut(id = "cat-dining", name = "Dining", shared = true),
                CategoryOut(id = "cat-groceries", name = "Groceries", shared = true),
            ),
        ),
        onBack = {},
        onSubmit = { _, _, _, _, _ -> },
    )
}

@Composable
private fun SplitSheetScene() {
    SplitSheetContent(
        txn = TransactionOut(
            id = "1", accountId = "a", amount = -5000, currency = "USD", date = "2026-07-15",
            status = "pending", merchantRaw = "MEIJER", merchantNorm = "MEIJER", categoryId = null,
            kind = "spend", transferGroup = null, reviewState = "needs_review", source = "email",
            matchedRuleId = null, ruleNote = null, aiSuggestedCategoryId = null,
            createdAt = "2026-07-15T00:00:00Z",
        ),
        categoryNames = mapOf("cat-groc" to "Groceries", "cat-cash" to "Cash"),
        onSplit = {},
    )
}

@Composable
private fun TxnScene(state: TransactionsUiState) {
    TransactionsContent(
        state = state,
        onSetFilter = {},
        onSetAccount = {},
        onSetQuery = {},
        onLoadMore = {},
        onRecategorize = { _, _ -> },
        onSplit = { _, _ -> },
        onDelete = {},
    )
}

@Composable
private fun TransactionsScene() {
    fun txn(id: String, merchant: String, amount: Long, kind: String, categoryId: String) =
        TransactionOut(
            id = id, accountId = "acct-1", amount = amount, currency = "USD", date = "2026-07-15",
            status = "posted", merchantRaw = merchant, merchantNorm = merchant,
            categoryId = categoryId, kind = kind, transferGroup = null, reviewState = "confirmed",
            source = "csv", matchedRuleId = null, ruleNote = null, aiSuggestedCategoryId = null,
            createdAt = "2026-07-15T00:00:00Z",
        )
    TxnScene(
        TransactionsUiState.Ready(
            items = listOf(
                txn("1", "XCEL ENERGY", -4500, "spend", "cat-util"),
                txn("2", "EMPLOYER PAYROLL", 450000, "income", "cat-income"),
                txn("3", "SAMPLE BISTRO", -3200, "spend", "cat-dining"),
            ),
            categoryNamesById = mapOf(
                "cat-util" to "Utilities", "cat-income" to "Income", "cat-dining" to "Dining",
            ),
            accounts = listOf(
                AccountOut("acct-1", "Checking", "US Bank", "depository", null, true, 318000, 0),
                AccountOut("acct-2", "Amex", "American Express", "card", "1234", true, -132000, null),
            ),
            categories = emptyList(),
            filter = TxnFilter.ALL,
            accountId = null,
            query = "",
            endReached = true,
        ),
    )
}

@Composable
private fun BottomBarScene() {
    MagpieBottomBar(currentRoute = Routes.HOME, onNavigate = {})
}

@Composable
private fun HomeReadyScene() {
    HomeContent(
        state = HomeUiState.Ready(
            summary = MonthlySummaryOut(
                year = 2026,
                month = 7,
                incomeCents = 450000,
                spendCents = -132000,
                netCents = 318000,
            ),
            accounts = emptyList(),
            greeting = "Good morning",
            reviewCount = 3,
            nextBill = UpcomingBillOut(
                biller = "XCEL ENERGY",
                amountDueCents = 4500,
                dueDate = "2026-07-18",
                accountName = "Checking",
                isOverdue = false,
                beforeNextPaycheck = true,
            ),
            safeToSpendCents = 74000,
            history = listOf(
                MonthSummaryOut(2026, 2, 450000, -410000, 40000),
                MonthSummaryOut(2026, 3, 450000, -382000, 68000),
                MonthSummaryOut(2026, 4, 460000, -455000, 5000),
                MonthSummaryOut(2026, 5, 450000, -390000, 60000),
                MonthSummaryOut(2026, 6, 470000, -402000, 68000),
                MonthSummaryOut(2026, 7, 450000, -132000, 318000),
            ),
            insight = MonthlyInsightOut(
                month = "2026-07-01",
                incomeCents = 450000,
                spendCents = 132000,
                netCents = 318000,
                categoryChanges = listOf(
                    CategoryChangeOut("Dining", thisMonthCents = 70000,
                        trailingMedianCents = 30000, deltaCents = 40000),
                ),
                budgetVerdicts = emptyList(),
                narrativeHeadline = "Dining up this month",
                narrativeSummary = "Dining ran higher than its usual $300, about $400 over.",
                narrativeSource = "llm",
            ),
        ),
        onAddTransaction = {},
        onViewAccounts = {},
        onViewReviewQueue = {},
        onViewCashflow = {},
        onViewRules = {},
        onViewTrends = {},
        onCreateFirstAccount = { _, _, _, _ -> },
    )
}

@Composable
private fun HomeNeedsAccountScene() {
    HomeContent(
        state = HomeUiState.NeedsAccount,
        onAddTransaction = {},
        onViewAccounts = {},
        onViewReviewQueue = {},
        onViewCashflow = {},
        onViewRules = {},
        onViewTrends = {},
        onCreateFirstAccount = { _, _, _, _ -> },
    )
}

@Composable
private fun AccountsScene() {
    AccountsContent(
        state = AccountsUiState(
            accounts = listOf(
                AccountOut(
                    id = "1",
                    name = "Checking",
                    institution = "US Bank",
                    type = "depository",
                    last4 = null,
                    active = true,
                    balanceCents = 318000,
                    balanceDeltaCents = 0,
                ),
                AccountOut(
                    id = "2",
                    name = "Amex",
                    institution = "American Express",
                    type = "card",
                    last4 = "1234",
                    active = true,
                    balanceCents = -132000,
                    balanceDeltaCents = null,
                ),
            ),
            loading = false,
        ),
        onBack = {},
        onStartImport = {},
        onDismissImportResult = {},
        onAddAccount = { _, _, _, _ -> },
        onDelete = {},
        onEnterBalance = { _, _, _ -> },
    )
}

@Composable
private fun ReviewQueueScene() {
    ReviewQueueContent(
        state = ReviewQueueUiState(
            transactions = listOf(
                TransactionOut(
                    id = "1",
                    accountId = "acct-1",
                    amount = -3500,
                    currency = "USD",
                    date = "2026-07-15",
                    status = "posted",
                    merchantRaw = "XCEL ENERGY",
                    merchantNorm = "XCEL ENERGY",
                    categoryId = null,
                    kind = "spend",
                    transferGroup = null,
                    reviewState = "needs_review",
                    source = "csv",
                    matchedRuleId = "rule-1",
                    ruleNote = "Looks like XCEL ENERGY, 2/3 observations",
                    createdAt = "2026-07-15T00:00:00Z",
                ),
                TransactionOut(
                    id = "2",
                    accountId = "acct-1",
                    amount = -1899,
                    currency = "USD",
                    date = "2026-07-14",
                    status = "posted",
                    merchantRaw = "SAMPLE STORE ONLINE",
                    merchantNorm = "SAMPLE STORE ONLINE",
                    categoryId = null,
                    kind = "spend",
                    transferGroup = null,
                    reviewState = "needs_review",
                    source = "email",
                    matchedRuleId = null,
                    ruleNote = null,
                    createdAt = "2026-07-14T00:00:00Z",
                ),
                TransactionOut(
                    id = "3",
                    accountId = "acct-1",
                    amount = -3200,
                    currency = "USD",
                    date = "2026-07-13",
                    status = "posted",
                    merchantRaw = "SAMPLE BISTRO",
                    merchantNorm = "SAMPLE BISTRO",
                    categoryId = null,
                    kind = "spend",
                    transferGroup = null,
                    reviewState = "needs_review",
                    source = "csv",
                    matchedRuleId = null,
                    ruleNote = null,
                    aiSuggestedCategoryId = "cat-dining",
                    createdAt = "2026-07-13T00:00:00Z",
                ),
            ),
            categories = listOf(
                CategoryOut(id = "cat-dining", name = "Dining", shared = true),
                CategoryOut(id = "cat-groceries", name = "Groceries", shared = true),
                CategoryOut(id = "cat-utilities", name = "Utilities", shared = true),
            ),
            categoryNamesById = mapOf("cat-dining" to "Dining"),
            loading = false,
        ),
        onBack = {},
        onConfirm = { _, _, _, _ -> },
    )
}

@Composable
private fun SettingsScene() {
    SettingsContent(
        state = SettingsUiState(
            categories = listOf(
                CategoryOut(id = "1", name = "Coffee runs", shared = false),
                CategoryOut(id = "2", name = "Dining", shared = true),
                CategoryOut(id = "3", name = "Groceries", shared = true),
                CategoryOut(id = "4", name = "Utilities", shared = true),
            ),
            userName = "Chris Raab",
            userEmail = "chris@dragonflymedia.org",
            serverVersion = "0.1.0",
            serverCommit = "2ebb651",
            loading = false,
        ),
        onBack = {},
        onAddCategory = {},
        onRenameCategory = { _, _ -> },
        onDeleteCategory = {},
    )
}

@Composable
private fun RulesScene() {
    RulesContent(
        state = RulesUiState(
            rules = listOf(
                RuleRow(
                    id = "1",
                    typeLabel = "Income",
                    matcher = "EMPLOYER PAYROLL",
                    summary = "biweekly Â±3d",
                    enabled = true,
                ),
                RuleRow(
                    id = "2",
                    typeLabel = "Bill",
                    matcher = "XCEL ENERGY",
                    summary = "monthly Â±20% Â· â†' Utilities",
                    enabled = true,
                ),
                RuleRow(
                    id = "3",
                    typeLabel = "Category rule",
                    matcher = "SAMPLE BISTRO",
                    summary = "â†' Dining",
                    enabled = false,
                ),
            ),
            loading = false,
            // The "create rules from your history" banner (#25) is part of this screen's story.
            suggestedRuleCount = 22,
        ),
        onBack = {},
        onSetEnabled = { _, _ -> },
        onDelete = {},
        onCreateSuggested = {},
    )
}

@Composable
private fun ChatScene() {
    ChatContent(
        state = ChatUiState(
            messages = listOf(
                ChatMessage("user", "How much did we spend on dining vs May?"),
                ChatMessage("assistant", "In June you spent $561.71 on dining; in May it was $1,183.17, about half as much."),
                ChatMessage("user", "What are my biggest recurring charges?"),
                ChatMessage("assistant", "Your largest recurring charges are the mortgage and school tuition; together they're most of your recurring cost."),
            ),
        ),
        onBack = {},
        onSend = {},
    )
}

@Composable
private fun SubscriptionsScene() {
    SubscriptionsContent(
        state = SubscriptionsUiState(
            subscriptions = listOf(
                SubscriptionOut("NETFLIX", "monthly", 1599, 12, "2026-07-01", 1899, 19188),
                SubscriptionOut("SPOTIFY", "monthly", 1099, 10, "2026-07-01", 1099, 13188),
                // Fitness-tagged: shows Spotter's cost-per-visit line (Link G).
                SubscriptionOut(
                    "THE GYM", "monthly", 5000, 8, "2026-06-15", 5000, 60000,
                    tags = listOf("fitness"), visitsThisMonth = 12, costPerVisitCents = 417,
                ),
            ),
            totalAnnualCostCents = 92376,
            loading = false,
        ),
        onBack = {},
    )
}

@Composable
private fun BudgetsScene() {
    BudgetsContent(
        state = BudgetsUiState(
            monthLabel = "July 2026",
            rows = listOf(
                BudgetRow(
                    id = "1", categoryId = "c1", categoryName = "Dining",
                    amountCents = 20000, spentCents = 26500,
                    projectedCents = 54900, dailyAllowanceCents = 0, paceStatus = "over",
                ),
                BudgetRow(
                    id = "2", categoryId = "c2", categoryName = "Groceries",
                    amountCents = 60000, spentCents = 41200,
                    projectedCents = 63800, dailyAllowanceCents = 1100, paceStatus = "watch",
                ),
                BudgetRow(
                    id = "3", categoryId = "c3", categoryName = "Transport",
                    amountCents = 15000, spentCents = 3000,
                    projectedCents = 4600, dailyAllowanceCents = 750, paceStatus = "on_track",
                ),
            ),
            categories = emptyList(),
            goal = GoalOut(
                id = "g1", kind = "monthly_savings", amountCents = 50000,
                createdAt = "2026-07-01T00:00:00Z",
            ),
            net = NetProjectionOut(
                mtdIncomeCents = 250000, mtdSpendCents = 190000,
                projectedIncomeCents = 400000, projectedSpendCents = 368000,
                projectedNetCents = 32000, basis = "blend", goalDeltaCents = -18000,
            ),
            daysLeft = 16,
            coachHeadline = "Dining is running the month hot",
            coachCoaching = "Dining is already $65 over its $200 budget and pacing toward " +
                "$549. Groceries can still land on budget at about $11/day.",
            uncategorizedMtdCents = 4200,
            loading = false,
        ),
        onBack = {},
        onAddBudget = { _, _ -> },
    )
}

@Composable
private fun CashflowScene() {
    CashflowContent(
        state = CashflowUiState(
            calendar = CashflowCalendarOut(
                nextPaycheckDate = "2026-07-31",
                totalDueBeforePaycheckCents = 10500,
                bills = listOf(
                    UpcomingBillOut(
                        biller = "SAMPLE INTERNET CO",
                        amountDueCents = 6000,
                        dueDate = "2026-07-18",
                        accountName = "Checking",
                        isOverdue = false,
                        beforeNextPaycheck = true,
                    ),
                    UpcomingBillOut(
                        biller = "XCEL ENERGY",
                        amountDueCents = 4500,
                        dueDate = "2026-07-10",
                        accountName = "Checking",
                        isOverdue = true,
                        beforeNextPaycheck = true,
                    ),
                    UpcomingBillOut(
                        biller = "SAMPLE RENT",
                        amountDueCents = 150000,
                        dueDate = "2026-08-05",
                        accountName = "Checking",
                        isOverdue = false,
                        beforeNextPaycheck = false,
                    ),
                ),
            ),
            loading = false,
        ),
        onBack = {},
    )
}

@Composable
private fun BillsScene() {
    BillsContent(
        state = BillsUiState(
            bills = listOf(
                BillOut(
                    id = "1",
                    biller = "XCEL ENERGY",
                    accountId = "acct-1",
                    amountDue = 4500,
                    dueDate = "2026-07-15",
                    issuedAt = "2026-06-15T00:00:00Z",
                    matchedTransactionId = "txn-1",
                    isMissing = false,
                ),
                BillOut(
                    id = "2",
                    biller = "SAMPLE INTERNET CO",
                    accountId = "acct-1",
                    amountDue = 6000,
                    dueDate = "2026-06-20",
                    issuedAt = "2026-05-20T00:00:00Z",
                    matchedTransactionId = null,
                    isMissing = true,
                ),
            ),
            loading = false,
        ),
        onBack = {},
    )
}
