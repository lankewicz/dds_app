package com.chicoeletro.dds.features.online.token

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface TokenApi {

    @GET("/health")
    suspend fun health(): HealthResponse

    @POST("/token")
    suspend fun getCombinedToken(
        @Body body: TokenRequestDto
    ): CombinedTokenResponseDto
}


data class HealthResponse(
    val status: String,
    val time: Long
)