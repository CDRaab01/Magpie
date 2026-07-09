package com.magpie.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ReceiptLong
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.PieChart
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.ui.graphics.vector.ImageVector

/**
 * The bottom-bar tabs (V1.md Tier 4 #27) — mirrors Cookbook's `TopLevelDestination`. The
 * review queue is deliberately *not* a tab (it's a task reached from Home's badge, not a place);
 * likewise Accounts / Cash flow / Rules are secondary screens reached from Home or Settings.
 * "Activity" is the short label for Transactions so five tabs fit the bar.
 */
enum class TopLevelDestination(val route: String, val label: String, val icon: ImageVector) {
    Home(Routes.HOME, "Home", Icons.Outlined.Home),
    Transactions(Routes.TRANSACTIONS, "Activity", Icons.AutoMirrored.Outlined.ReceiptLong),
    Bills(Routes.BILLS, "Bills", Icons.Outlined.CalendarMonth),
    Budgets(Routes.BUDGETS, "Budgets", Icons.Outlined.PieChart),
    Settings(Routes.SETTINGS, "Settings", Icons.Outlined.Settings),
}
