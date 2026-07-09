package com.magpie.ui.navigation

import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.magpie.ui.theme.MagpieTheme

/**
 * PULSE-flavored bottom navigation (V1.md Tier 4 #27) — mirrors `CookbookBottomBar`, with Magpie's
 * teal money channel for selection. Only shown on the top-level tabs; the nav host hides it on the
 * sign-in and detail screens.
 */
@Composable
fun MagpieBottomBar(
    currentRoute: String?,
    onNavigate: (TopLevelDestination) -> Unit,
) {
    val money = MagpieTheme.colors.money
    NavigationBar {
        TopLevelDestination.entries.forEach { destination ->
            NavigationBarItem(
                selected = currentRoute == destination.route,
                onClick = { onNavigate(destination) },
                icon = { Icon(destination.icon, contentDescription = destination.label) },
                label = { Text(destination.label) },
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
