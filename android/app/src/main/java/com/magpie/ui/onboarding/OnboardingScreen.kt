package com.magpie.ui.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.magpie.ui.theme.MagpieTheme
import design.pulse.ui.components.PulseButton
import design.pulse.ui.components.SectionHeader

@Composable
fun OnboardingScreen(onDone: () -> Unit) {
    val viewModel: OnboardingViewModel = hiltViewModel()
    val saving by viewModel.saving.collectAsStateWithLifecycle()
    val error by viewModel.error.collectAsStateWithLifecycle()
    var step by remember { mutableIntStateOf(0) }

    OnboardingContent(
        step = step,
        saving = saving,
        error = error,
        onGetStarted = { step = 1 },
        onAddAccount = { name, inst, type, last4 ->
            viewModel.addAccount(name, inst, type, last4) { step = 2 }
        },
        onNext = { step += 1 },
        onFinish = { viewModel.finish(onDone) },
        onSkip = { viewModel.finish(onDone) },
    )
}

private const val STEP_COUNT = 4

/** Pure guided first-run (screenshot-testable): welcome -> add account -> import -> budgets. */
@Composable
internal fun OnboardingContent(
    step: Int,
    saving: Boolean,
    error: String?,
    onGetStarted: () -> Unit,
    onAddAccount: (name: String, institution: String, type: String, last4: String?) -> Unit,
    onNext: () -> Unit,
    onFinish: () -> Unit,
    onSkip: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(MagpieTheme.spacing.lg)
            .verticalScroll(rememberScrollState()),
    ) {
        StepDots(step = step, count = STEP_COUNT)
        Spacer(Modifier.height(20.dp))
        when (step) {
            0 -> WelcomeStep(onGetStarted, onSkip)
            1 -> AddAccountStep(saving, error, onAddAccount)
            2 -> InfoStep(
                title = "Import your history",
                body = "On the Accounts tab you can import a CSV from each bank. A year of history " +
                    "seeds your budgets and category suggestions, so Magpie isn't asking about " +
                    "everything on day one. You can always do this later.",
                primary = "Next",
                onPrimary = onNext,
                onSkip = onSkip,
            )
            3 -> InfoStep(
                title = "Set budgets",
                body = "On the Budgets tab, set a monthly amount per category to see month-vs-budget " +
                    "at a glance. Optional — Magpie tracks your cash flow either way.",
                primary = "Finish",
                onPrimary = onFinish,
                onSkip = null,
            )
        }
    }
}

@Composable
private fun StepDots(step: Int, count: Int) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        repeat(count) { i ->
            val on = i <= step
            Text(
                text = if (on) "●" else "○",
                color = if (on) MagpieTheme.colors.money.base
                else MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun WelcomeStep(onGetStarted: () -> Unit, onSkip: () -> Unit) {
    Column {
        Text("Welcome to Magpie", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(8.dp))
        Text(
            "Household cash flow, assembled automatically from your banks' alert emails — you " +
                "review, you don't type it all in.",
            style = MaterialTheme.typography.bodyLarge,
        )
        Spacer(Modifier.height(20.dp))
        Bullet("Add your accounts")
        Bullet("Import your history (optional)")
        Bullet("Review the queue — a ten-second daily habit")
        Spacer(Modifier.height(28.dp))
        PulseButton(text = "Get started", onClick = onGetStarted, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        PulseButton(text = "Skip for now", tonal = true, onClick = onSkip, modifier = Modifier.fillMaxWidth())
    }
}

@Composable
private fun Bullet(text: String) {
    Row(Modifier.padding(vertical = 4.dp)) {
        Text("•  ", color = MagpieTheme.colors.money.base)
        Text(text, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun AddAccountStep(
    saving: Boolean,
    error: String?,
    onAddAccount: (String, String, String, String?) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var institution by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("card") }
    var last4 by remember { mutableStateOf("") }

    Column {
        SectionHeader(label = "Add your first account", channel = MagpieTheme.colors.money.base)
        Spacer(Modifier.height(8.dp))
        TextField(name, { name = it }, label = { Text("Name (e.g. Amex)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        TextField(institution, { institution = it }, label = { Text("Institution") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            PulseButton(text = "Card", tonal = type != "card", compact = true, onClick = { type = "card" })
            PulseButton(text = "Checking", tonal = type != "depository", compact = true, onClick = { type = "depository" })
        }
        Spacer(Modifier.height(8.dp))
        TextField(
            value = last4,
            onValueChange = { if (it.length <= 4 && it.all(Char::isDigit)) last4 = it },
            label = { Text("Last 4 digits") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth(),
        )
        // The last-4 is how alert emails match to this account — worth getting right (the bug the
        // owner hit was a blank last-4 on the first Amex).
        Text(
            "Alert emails match to the account by these digits.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
        error?.let {
            Spacer(Modifier.height(8.dp))
            Text(it, color = MaterialTheme.colorScheme.error)
        }
        Spacer(Modifier.height(24.dp))
        PulseButton(
            text = if (saving) "Adding…" else "Add account",
            enabled = !saving && name.isNotBlank() && institution.isNotBlank(),
            onClick = { onAddAccount(name.trim(), institution.trim(), type, last4.ifBlank { null }) },
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun InfoStep(
    title: String,
    body: String,
    primary: String,
    onPrimary: () -> Unit,
    onSkip: (() -> Unit)?,
) {
    Column {
        Text(title, style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(12.dp))
        Text(body, style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.height(28.dp))
        PulseButton(text = primary, onClick = onPrimary, modifier = Modifier.fillMaxWidth())
        onSkip?.let {
            Spacer(Modifier.height(8.dp))
            PulseButton(text = "Skip", tonal = true, onClick = it, modifier = Modifier.fillMaxWidth())
        }
    }
}
