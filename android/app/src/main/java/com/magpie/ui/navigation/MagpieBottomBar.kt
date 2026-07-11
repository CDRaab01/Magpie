package com.magpie.ui.navigation

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.magpie.ui.theme.MagpieTheme

/**
 * PULSE bottom navigation, reworked to match the sibling apps (Spotter's `PulseBottomBar`,
 * Plate's `PlateBottomBar`): a flat panel with a 1dp hairline top rule instead of an elevated
 * surface, and a filled icon on the active tab (outlined when unselected). Selection stays in
 * Magpie's teal money channel — unlike Plate's per-tab macro tints, Magpie's other channels
 * (green/amber/red) carry budget semantics (#31 color grammar), so they'd misread as tab decoration.
 *
 * Only shown on the top-level tabs; the nav host hides it on the sign-in and detail screens.
 */
@Composable
fun MagpieBottomBar(
    currentRoute: String?,
    onNavigate: (TopLevelDestination) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = MagpieTheme.colors
    val money = colors.money
    Column(modifier) {
        HorizontalDivider(thickness = 1.dp, color = colors.hairline)
        NavigationBar(
            containerColor = colors.panel,
            tonalElevation = 0.dp,
        ) {
            TopLevelDestination.entries.forEach { destination ->
                val selected = currentRoute == destination.route
                NavigationBarItem(
                    selected = selected,
                    onClick = { onNavigate(destination) },
                    icon = {
                        Icon(
                            imageVector = if (selected) destination.selectedIcon else destination.icon,
                            contentDescription = destination.label,
                        )
                    },
                    label = { Text(destination.label, style = MaterialTheme.typography.labelMedium) },
                    colors = NavigationBarItemDefaults.colors(
                        selectedIconColor = money.base,
                        selectedTextColor = money.base,
                        indicatorColor = money.dim,
                        unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                        unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    ),
                )
            }
        }
    }
}
