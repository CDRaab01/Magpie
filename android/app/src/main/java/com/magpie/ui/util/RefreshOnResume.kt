package com.magpie.ui.util

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

/**
 * Re-runs [onRefresh] whenever the screen resumes (mirrors Cookbook's home/pantry pattern). List
 * screens keep their ViewModel across bottom-nav tab switches (save/restoreState), so without this
 * they show whatever they last loaded — stale after data changes elsewhere (a new alert filing, an
 * account edit, a server-side replay). Firing on ON_RESUME keeps them current with no pull-to-refresh
 * needed, and re-fetching a small tailnet payload each time a tab is shown is cheap.
 */
@Composable
fun RefreshOnResume(onRefresh: () -> Unit) {
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) onRefresh()
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
}
