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
import com.magpie.data.remote.TransactionOut
import com.magpie.data.remote.BillOut
import com.magpie.data.remote.CashflowCalendarOut
import com.magpie.data.remote.UpcomingBillOut
import com.magpie.ui.accounts.AccountsContent
import com.magpie.ui.accounts.AccountsUiState
import com.magpie.ui.bills.BillsContent
import com.magpie.ui.bills.BillsUiState
import com.magpie.ui.budgets.BudgetRow
import com.magpie.ui.budgets.BudgetsContent
import com.magpie.ui.budgets.BudgetsUiState
import com.magpie.ui.cashflow.CashflowContent
import com.magpie.ui.cashflow.CashflowUiState
import com.magpie.ui.rules.RuleRow
import com.magpie.ui.rules.RulesContent
import com.magpie.ui.rules.RulesUiState
import com.magpie.ui.home.HomeContent
import com.magpie.ui.home.HomeUiState
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
 * JVM screenshot tests (Robolectric native graphics + Roborazzi) — render Magpie's first real
 * screen to PNGs without a device or emulator. Run with `:app:testDebugUnitTest`; images land
 * in `app/screenshots/`. Record with `-Proborazzi.test.record=true`. Mirrors the suite reference
 * (Plate/Cookbook's `ScreenshotTest`) — screenshot the pure Content composable, not the
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
        ),
        onAddTransaction = {},
        onViewTransactions = {},
        onViewAccounts = {},
        onViewReviewQueue = {},
        onViewBills = {},
        onViewCashflow = {},
        onViewBudgets = {},
        onViewRules = {},
        onViewSettings = {},
        onCreateFirstAccount = { _, _, _ -> },
    )
}

@Composable
private fun HomeNeedsAccountScene() {
    HomeContent(
        state = HomeUiState.NeedsAccount,
        onAddTransaction = {},
        onViewTransactions = {},
        onViewAccounts = {},
        onViewReviewQueue = {},
        onViewBills = {},
        onViewCashflow = {},
        onViewBudgets = {},
        onViewRules = {},
        onViewSettings = {},
        onCreateFirstAccount = { _, _, _ -> },
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
                    summary = "biweekly ±3d",
                    enabled = true,
                ),
                RuleRow(
                    id = "2",
                    typeLabel = "Bill",
                    matcher = "XCEL ENERGY",
                    summary = "monthly ±20% · → Utilities",
                    enabled = true,
                ),
                RuleRow(
                    id = "3",
                    typeLabel = "Category rule",
                    matcher = "SAMPLE BISTRO",
                    summary = "→ Dining",
                    enabled = false,
                ),
            ),
            loading = false,
        ),
        onBack = {},
        onSetEnabled = { _, _ -> },
        onDelete = {},
    )
}

@Composable
private fun BudgetsScene() {
    BudgetsContent(
        state = BudgetsUiState(
            monthLabel = "July 2026",
            rows = listOf(
                BudgetRow(id = "1", categoryName = "Dining", amountCents = 20000, spentCents = 26500),
                BudgetRow(id = "2", categoryName = "Groceries", amountCents = 60000, spentCents = 41200),
                BudgetRow(id = "3", categoryName = "Transport", amountCents = 15000, spentCents = 3000),
            ),
            categories = emptyList(),
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
