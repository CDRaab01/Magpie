package com.magpie.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class HouseholdMemberOut(
    @SerialName("user_id") val userId: String,
    val name: String,
    val email: String,
    @SerialName("is_owner") val isOwner: Boolean,
)

@Serializable
data class HouseholdOut(
    val members: List<HouseholdMemberOut>,
    @SerialName("you_are_owner") val youAreOwner: Boolean,
    // True once the ledger is actually shared (more than one member).
    val shared: Boolean,
)

@Serializable
data class AddMemberRequest(val email: String)
