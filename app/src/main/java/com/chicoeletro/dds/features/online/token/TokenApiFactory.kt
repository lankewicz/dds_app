// Módulo: app/src/main/java/com/chicoeletro/dds/features/online/token/TokenApiFactory.kt
// Função: Fábrica de instâncias da API de tokens. Configura o cliente HTTP (OkHttp/Retrofit) 
//         com logs de depuração e serialização para comunicação com o backend.
// Tecnologias: Retrofit, OkHttp, Kotlinx Serialization.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.online.token

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import okhttp3.OkHttpClient
import okhttp3.Interceptor
import java.util.concurrent.TimeUnit
import com.chicoeletro.dds.core.agora.AgoraConfig

object TokenApiFactory {

    // Render (produção/teste remoto)
    // Importante: Retrofit exige que baseUrl termine com "/"
    private const val BASE_URL = AgoraConfig.TOKEN_BASE_URL

    val api: TokenApi by lazy {
        val client = OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .callTimeout(60, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()

        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(TokenApi::class.java)
    }
}