package com.magpie

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.magpie.ui.navigation.MagpieNavHost
import com.magpie.ui.theme.MagpieTheme
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.flow.MutableStateFlow

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    // #34: the host of the `magpie://<host>` deep link that launched (or re-launched) the app from
    // an ntfy alert, e.g. "bills". MagpieNavHost observes this and routes once signed in.
    private val deepLinkHost = MutableStateFlow(intentHost(intent))

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MagpieTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    MagpieNavHost(deepLinkHost = deepLinkHost)
                }
            }
        }
    }

    // launchMode=singleTask (manifest) routes a tap on a later alert here instead of a new activity.
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        deepLinkHost.value = intentHost(intent)
    }

    private fun intentHost(intent: Intent?): String? =
        intent?.data?.takeIf { it.scheme == "magpie" }?.host
}
