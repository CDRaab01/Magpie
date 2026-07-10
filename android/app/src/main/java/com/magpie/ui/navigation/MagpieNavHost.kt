package com.magpie.ui.navigation

import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.magpie.ui.accounts.AccountsScreen
import com.magpie.ui.bills.BillsScreen
import com.magpie.ui.budgets.BudgetsScreen
import com.magpie.ui.cashentry.CashEntryScreen
import com.magpie.ui.cashflow.CashflowScreen
import com.magpie.ui.home.HomeScreen
import com.magpie.ui.reviewqueue.ReviewQueueScreen
import com.magpie.ui.rules.RulesScreen
import com.magpie.ui.settings.SettingsScreen
import com.magpie.ui.signin.SignInScreen
import com.magpie.ui.merchant.MerchantDetailScreen
import com.magpie.ui.transactions.TransactionsScreen
import com.magpie.ui.subscriptions.SubscriptionsScreen
import com.magpie.ui.trends.TrendsScreen

/**
 * Gated on [AuthGateViewModel.isSignedIn]: `null` briefly while DataStore's first read lands,
 * then either [SignInScreen] or the signed-in graph — no explicit post-sign-in navigation call is
 * needed, since saving a session makes the underlying Flow re-emit and this recomposes.
 */
@Composable
fun MagpieNavHost(deepLinkHost: StateFlow<String?> = MutableStateFlow(null)) {
    val authGateViewModel: AuthGateViewModel = hiltViewModel()
    val isSignedIn by authGateViewModel.isSignedIn.collectAsStateWithLifecycle()

    when (isSignedIn) {
        null -> Unit
        false -> SignInScreen()
        true -> SignedInOrOnboarding(deepLinkHost = deepLinkHost)
    }
}

/** Signed in: show the guided first-run (#33) on a fresh install, otherwise the main graph. */
@Composable
private fun SignedInOrOnboarding(deepLinkHost: StateFlow<String?>) {
    val onboardingViewModel: com.magpie.ui.onboarding.OnboardingViewModel = hiltViewModel()
    val shouldOnboard by onboardingViewModel.shouldShow.collectAsStateWithLifecycle()
    when (shouldOnboard) {
        null -> Unit
        true -> com.magpie.ui.onboarding.OnboardingScreen(onDone = {})
        false -> SignedInGraph(deepLinkHost = deepLinkHost)
    }
}

/** #34: map an ntfy `magpie://<host>` deep link to the route that lets the owner act on the alert. */
private fun routeForDeepLink(host: String?): String? = when (host) {
    "bills" -> Routes.BILLS
    "cashflow" -> Routes.CASHFLOW
    "accounts" -> Routes.ACCOUNTS
    "review" -> Routes.REVIEW_QUEUE
    "transactions" -> Routes.TRANSACTIONS
    "home" -> Routes.HOME
    "subscriptions" -> Routes.SUBSCRIPTIONS
    else -> null
}

/**
 * The signed-in shell (Tier 4 #27): a [MagpieBottomBar] over the graph, shown only on the top-level
 * tabs. Tab switches go through [goTab] (Cookbook's pattern — save/restore each tab's state and keep
 * a single instance), so bouncing between tabs doesn't stack them; secondary screens (Accounts,
 * Review queue, Cash flow, Rules, Cash entry) are pushed normally and keep their own back button.
 */
@Composable
private fun SignedInGraph(deepLinkHost: StateFlow<String?> = MutableStateFlow(null)) {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val isTopLevel = TopLevelDestination.entries.any { it.route == currentRoute }

    // #34: when an alert deep link arrives (signed in), navigate to its screen once, then clear it.
    val deepHost by deepLinkHost.collectAsStateWithLifecycle()
    LaunchedEffect(deepHost) {
        val route = routeForDeepLink(deepHost) ?: return@LaunchedEffect
        navController.navigate(route) { launchSingleTop = true }
        (deepLinkHost as? MutableStateFlow<String?>)?.value = null
    }

    val goTab: (String) -> Unit = { route ->
        navController.navigate(route) {
            popUpTo(navController.graph.findStartDestination().id) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }

    Scaffold(
        bottomBar = {
            if (isTopLevel) {
                MagpieBottomBar(currentRoute = currentRoute, onNavigate = { goTab(it.route) })
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Routes.HOME,
            // consumeWindowInsets so each screen's own inner Scaffold/TopAppBar doesn't re-apply the
            // same system-bar insets a second time (the double-gap bug the siblings hit first).
            modifier = Modifier.padding(padding).consumeWindowInsets(padding),
        ) {
            composable(Routes.HOME) { HomeScreen(navController) }
            composable(Routes.TRANSACTIONS) { TransactionsScreen(navController) }
            composable(Routes.CASH_ENTRY) { CashEntryScreen(navController) }
            composable(Routes.ACCOUNTS) { AccountsScreen(navController) }
            composable(Routes.REVIEW_QUEUE) { ReviewQueueScreen(navController) }
            composable(Routes.BILLS) { BillsScreen(navController) }
            composable(Routes.CASHFLOW) { CashflowScreen(navController) }
            composable(Routes.BUDGETS) { BudgetsScreen(navController) }
            composable(Routes.RULES) { RulesScreen(navController) }
            composable(Routes.TRENDS) { TrendsScreen(navController) }
            composable(Routes.SUBSCRIPTIONS) { SubscriptionsScreen(navController) }
            composable(Routes.MERCHANT_DETAIL) { entry ->
                val merchant = entry.arguments?.getString("merchant")
                    ?.let { java.net.URLDecoder.decode(it, "UTF-8") }
                    .orEmpty()
                MerchantDetailScreen(navController, merchant)
            }
            composable(Routes.SETTINGS) { SettingsScreen(navController) }
        }
    }
}
