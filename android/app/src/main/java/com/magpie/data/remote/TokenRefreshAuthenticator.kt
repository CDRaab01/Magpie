package com.magpie.data.remote

import com.magpie.BuildConfig
import com.magpie.data.local.TokenStore
import com.magpie.util.AuthEventBus
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route

/**
 * Refreshes an expired access token on a 401 and retries the original request, so a normal
 * 30-minute access-token expiry doesn't bounce the user back into the browser sign-in flow.
 * Mirrors Spotter/Cookbook's hardened authenticator: refreshes are serialized, only an explicit
 * auth rejection signs the user out, and a transient network failure mid-refresh keeps the
 * session intact.
 */
@Singleton
class TokenRefreshAuthenticator @Inject constructor(
    private val tokenStore: TokenStore,
    private val authEventBus: AuthEventBus,
) : okhttp3.Authenticator {

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val refreshClient = OkHttpClient()
    private val refreshLock = Any()

    override fun authenticate(route: Route?, response: Response): Request? {
        // A 401 from the auth endpoints themselves means an invalid/garbage token — not an
        // expired access token. Don't refresh and never sign out here: that would clear tokens
        // and bounce a failed sign-in attempt into a confusing state.
        if (response.request.url.encodedPath.contains("/auth/")) return null

        if (responseCount(response) >= 2) return signOut()

        synchronized(refreshLock) {
            val failedToken = response.request.header("Authorization")?.removePrefix("Bearer ")
            val storedToken = runBlocking { tokenStore.accessToken.firstOrNull() }
            if (storedToken != null && storedToken != failedToken) {
                return response.request.newBuilder()
                    .header("Authorization", "Bearer $storedToken")
                    .build()
            }

            val refreshToken = runBlocking { tokenStore.refreshToken.firstOrNull() } ?: return signOut()

            val refreshUrl = BuildConfig.SERVER_URL.trimEnd('/') + "/auth/refresh"
            val body = json.encodeToString(RefreshRequest(refreshToken))
                .toRequestBody("application/json".toMediaType())
            val refreshRequest = Request.Builder().url(refreshUrl).post(body).build()

            val refreshResponse = try {
                refreshClient.newCall(refreshRequest).execute()
            } catch (_: IOException) {
                return null // transient network failure — keep the session, retry later
            }

            if (refreshResponse.code == 401 || refreshResponse.code == 403) return signOut()
            if (!refreshResponse.isSuccessful) {
                refreshResponse.close()
                return null
            }

            val tokenResponse = try {
                val bodyStr = refreshResponse.body?.string() ?: return null
                json.decodeFromString<TokenResponse>(bodyStr)
            } catch (_: Exception) {
                return null
            }

            runBlocking { tokenStore.save(tokenResponse.accessToken, tokenResponse.refreshToken) }

            return response.request.newBuilder()
                .header("Authorization", "Bearer ${tokenResponse.accessToken}")
                .build()
        }
    }

    private fun responseCount(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) { count++; prior = prior.priorResponse }
        return count
    }

    private fun signOut(): Request? {
        runBlocking { tokenStore.clear() }
        authEventBus.emitLogout()
        return null
    }
}
