package com.magpie.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.magpie.ui.accounts.AccountsScreen
import com.magpie.ui.bills.BillsScreen
import com.magpie.ui.budgets.BudgetsScreen
import com.magpie.ui.cashflow.CashflowScreen
import com.magpie.ui.rules.RulesScreen
import com.magpie.ui.cashentry.CashEntryScreen
import com.magpie.ui.home.HomeScreen
import com.magpie.ui.reviewqueue.ReviewQueueScreen
import com.magpie.ui.settings.SettingsScreen
import com.magpie.ui.signin.SignInScreen
import com.magpie.ui.transactions.TransactionsScreen

/**
 * Gated on [AuthGateViewModel.isSignedIn]: `null` briefly while DataStore's first read lands,
 * then either [SignInScreen] or the main graph — no explicit post-sign-in navigation call is
 * needed, since saving a session makes the underlying Flow re-emit and this recomposes.
 */
@Composable
fun MagpieNavHost() {
    val authGateViewModel: AuthGateViewModel = hiltViewModel()
    val isSignedIn by authGateViewModel.isSignedIn.collectAsStateWithLifecycle()

    when (isSignedIn) {
        null -> Unit
        false -> SignInScreen()
        true -> {
            val navController = rememberNavController()
            NavHost(navController = navController, startDestination = Routes.HOME) {
                composable(Routes.HOME) { HomeScreen(navController) }
                composable(Routes.TRANSACTIONS) { TransactionsScreen(navController) }
                composable(Routes.CASH_ENTRY) { CashEntryScreen(navController) }
                composable(Routes.ACCOUNTS) { AccountsScreen(navController) }
                composable(Routes.REVIEW_QUEUE) { ReviewQueueScreen(navController) }
                composable(Routes.BILLS) { BillsScreen(navController) }
                composable(Routes.CASHFLOW) { CashflowScreen(navController) }
                composable(Routes.BUDGETS) { BudgetsScreen(navController) }
                composable(Routes.RULES) { RulesScreen(navController) }
                composable(Routes.SETTINGS) { SettingsScreen(navController) }
            }
        }
    }
}
