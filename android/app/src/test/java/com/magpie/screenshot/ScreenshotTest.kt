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
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.ui.accounts.AccountsContent
import com.magpie.ui.accounts.AccountsUiState
import com.magpie.ui.home.HomeContent
import com.magpie.ui.home.HomeUiState
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
        ),
        onAddTransaction = {},
        onViewTransactions = {},
        onViewAccounts = {},
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
