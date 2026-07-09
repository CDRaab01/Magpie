package com.magpie.ui.signin

import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.magpie.data.remote.SuiteAuthManager
import dagger.hilt.android.lifecycle.HiltViewModel
import design.pulse.ui.components.PulseButton
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@HiltViewModel
class SignInViewModel @Inject constructor(
    private val suiteAuthManager: SuiteAuthManager,
) : ViewModel() {
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    fun authorizeIntent(): Intent = suiteAuthManager.authorizeIntent()

    fun onSignInResult(data: Intent?) {
        viewModelScope.launch {
            try {
                suiteAuthManager.complete(data)
                _error.value = null
            } catch (e: Exception) {
                _error.value = e.message ?: "Sign-in failed"
            }
        }
    }
}

@Composable
fun SignInScreen() {
    val viewModel: SignInViewModel = hiltViewModel()
    val error by viewModel.error.collectAsStateWithLifecycle()
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result -> viewModel.onSignInResult(result.data) }

    SignInContent(
        error = error,
        onSignIn = { launcher.launch(viewModel.authorizeIntent()) },
    )
}

/** Pure presentation (screenshot-testable): the tailnet SSO landing. */
@Composable
internal fun SignInContent(error: String?, onSignIn: () -> Unit) {
    Box(modifier = Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("Magpie", style = MaterialTheme.typography.headlineLarge)
            Spacer(Modifier.height(8.dp))
            Text(
                "Household cash flow, private and tailnet-only.",
                style = MaterialTheme.typography.bodyMedium,
            )
            Spacer(Modifier.height(32.dp))
            PulseButton(text = "Sign in with Dragonfly", onClick = onSignIn)
            error?.let {
                Spacer(Modifier.height(16.dp))
                Text(it, color = MaterialTheme.colorScheme.error)
            }
        }
    }
}
