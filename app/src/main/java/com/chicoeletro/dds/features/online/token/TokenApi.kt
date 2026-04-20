// Módulo: app/src/main/java/com/chicoeletro/dds/features/online/token/TokenApi.kt
// Função: Interface Retrofit para obtenção de tokens RTC/RTM. Define os endpoints do servidor 
//         de tokens necessários para acesso seguro às reuniões do Agora.
// Tecnologias: Retrofit, REST API.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

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