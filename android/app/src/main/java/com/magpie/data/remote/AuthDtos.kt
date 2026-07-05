package com.magpie.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class RefreshRequest(
    @SerialName("refresh_token") val refreshToken: String,
)

@Serializable
data class SuiteLoginRequest(
    // A suite access token from the Dragonfly identity server.
    @SerialName("suite_token") val suiteToken: String,
)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("token_type") val tokenType: String = "bearer",
)

@Serializable
data class VersionOut(
    val name: String = "",
    val version: String = "",
    val commit: String = "unknown",
    @SerialName("built_at") val builtAt: String = "unknown",
)
