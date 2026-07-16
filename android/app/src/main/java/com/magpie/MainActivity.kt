package com.magpie

import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_STRONG
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.lifecycleScope
import com.magpie.data.local.AppLockStore
import com.magpie.security.AppLock
import com.magpie.ui.lock.LockScreen
import com.magpie.ui.navigation.MagpieNavHost
import com.magpie.ui.theme.MagpieTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

@AndroidEntryPoint
class MainActivity : FragmentActivity() {

    @Inject lateinit var appLock: AppLock
    @Inject lateinit var appLockStore: AppLockStore

    // #34: the routing token of the `magpie://…` intent that launched (or re-launched) the app —
    // either an ntfy alert deep link (`magpie://<host>`, e.g. "bills") or a static launcher
    // shortcut (`magpie://shortcut/<target>`, long-press the icon). Held here in the Activity so a
    // shortcut tapped from a cold start survives BOTH gates: MagpieNavHost is only composed once the
    // app lock is unlocked, and its routing only fires once signed in — so the token is consumed
    // (navigated to, then cleared) only after unlock AND sign-in, never dropped in between.
    private val deepLinkHost = MutableStateFlow(intentHost(intent))

    // Live snapshot of whether the lock is enabled, for the lifecycle callback.
    @Volatile private var lockEnabled = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // Lock immediately on a cold start if enabled — block briefly on the first read so no
        // financial content ever flashes before the gate.
        lockEnabled = runBlocking { appLockStore.enabled.first() }
        if (lockEnabled) appLock.lock()
        lifecycleScope.launch { appLockStore.enabled.collect { lockEnabled = it } }

        // Re-lock whenever the app leaves the foreground (a finance app shouldn't sit open).
        lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onStop(owner: LifecycleOwner) {
                if (lockEnabled) appLock.lock()
            }
        })

        setContent {
            MagpieTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    val locked by appLock.locked.collectAsState()
                    if (locked) {
                        // Auto-present the OS prompt when the gate appears; the button re-triggers it.
                        LaunchedEffect(Unit) { promptUnlock() }
                        LockScreen(onUnlock = ::promptUnlock)
                    } else {
                        MagpieNavHost(deepLinkHost = deepLinkHost)
                    }
                }
            }
        }
    }

    /**
     * Show the OS unlock prompt. Allows the device credential (PIN/pattern) alongside biometrics, so
     * there is always a fallback, and **fails open** when the device has neither enrolled — the lock
     * can never trap the owner out of their own finances.
     */
    private fun promptUnlock() {
        val allowed = BIOMETRIC_STRONG or DEVICE_CREDENTIAL
        if (BiometricManager.from(this).canAuthenticate(allowed) != BiometricManager.BIOMETRIC_SUCCESS) {
            appLock.unlock()
            return
        }
        val prompt = BiometricPrompt(
            this,
            ContextCompat.getMainExecutor(this),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    appLock.unlock()
                }
            },
        )
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Unlock Magpie")
            .setSubtitle("Your finances stay private")
            .setAllowedAuthenticators(allowed)
            .build()
        prompt.authenticate(info)
    }

    // launchMode=singleTask (manifest) routes a tap on a later alert here instead of a new activity.
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        deepLinkHost.value = intentHost(intent)
    }

    /**
     * The routing token for a `magpie://…` intent, or null. ntfy alert deep links arrive as
     * `magpie://<host>` and route directly by host. Static launcher shortcuts arrive as
     * `magpie://shortcut/<target>`; map each target onto the deep-link token MagpieNavHost already
     * routes so the two paths share one gate-surviving consume flow.
     */
    private fun intentHost(intent: Intent?): String? {
        val data = intent?.data?.takeIf { it.scheme == "magpie" } ?: return null
        return if (data.host == "shortcut") {
            when (data.lastPathSegment) {
                "review" -> "review" // → Review queue
                "add-cash" -> "cashentry" // → Cash entry
                "search" -> "transactions" // → Transaction search
                else -> null
            }
        } else {
            data.host
        }
    }
}
