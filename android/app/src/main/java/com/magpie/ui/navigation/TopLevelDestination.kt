package com.magpie.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.automirrored.outlined.ReceiptLong
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.PieChart
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.ui.graphics.vector.ImageVector

/**
 * The bottom-bar tabs (V1.md Tier 4 #27) — mirrors the sibling apps' `TopLevelDestination`
 * (Spotter/Plate). The review queue is deliberately *not* a tab (it's a task reached from Home's
 * badge, not a place); likewise Accounts / Cash flow / Rules are secondary screens reached from
 * Home or Settings. "Activity" is the short label for Transactions so five tabs fit the bar.
 *
 * Each tab carries an outlined [icon] (unselected) and a filled [selectedIcon] (selected), so the
 * active tab reads as filled — the Spotter/Plate bar grammar.
 */
enum class TopLevelDestination(
    val route: String,
    val label: String,
    val icon: ImageVector,
    val selectedIcon: ImageVector,
) {
    Home(Routes.HOME, "Home", Icons.Outlined.Home, Icons.Filled.Home),
    Transactions(
        Routes.TRANSACTIONS,
        "Activity",
        Icons.AutoMirrored.Outlined.ReceiptLong,
        Icons.AutoMirrored.Filled.ReceiptLong,
    ),
    Bills(Routes.BILLS, "Bills", Icons.Outlined.CalendarMonth, Icons.Filled.CalendarMonth),
    Budgets(Routes.BUDGETS, "Budgets", Icons.Outlined.PieChart, Icons.Filled.PieChart),
    Settings(Routes.SETTINGS, "Settings", Icons.Outlined.Settings, Icons.Filled.Settings),
}
