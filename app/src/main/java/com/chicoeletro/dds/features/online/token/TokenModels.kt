package com.chicoeletro.dds.features.online.token
import androidx.annotation.Keep
import com.google.gson.annotations.SerializedName

@Keep
data class TokenRequestDto(
    @SerializedName("channel")
    val channel: String,

    @SerializedName("uid")
    val uid: Int,

    @SerializedName("role")
    val role: String,

    @SerializedName("expire_seconds")
    val expire_seconds: Int,

    @SerializedName("api_key")
    val api_key: String?
)

data class CombinedTokenResponseDto(
    @SerializedName("rtc_token")
    val rtc_token: String,

    @SerializedName("rtm_token")
    val rtm_token: String,

    @SerializedName("expire_at")
    val expire_at: Long,

    @SerializedName("now")
    val now: Long,

    @SerializedName("channel")
    val channel: String,

    @SerializedName("uid")
    val uid: Int,

    @SerializedName("role")
    val role: String,

    @SerializedName("user_account")
    val user_account: String
)
