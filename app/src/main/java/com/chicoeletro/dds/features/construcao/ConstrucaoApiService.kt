// Módulo: app/src/main/java/com/chicoeletro/dds/features/construcao/ConstrucaoApiService.kt
// Função: Cliente de API e endpoints do módulo de Construção (Supervisor de Obras).
// Tecnologias: Retrofit, Gson Converter.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.features.construcao

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface ConstrucaoApiService {
    @GET("api/projetos")
    suspend fun getProjetos(): List<Projeto>

    @GET("api/projetos/{projeto_id}/estruturas")
    suspend fun getEstruturas(@Path("projeto_id") projetoId: String): List<Estrutura>

    @GET("api/estruturas/{estrutura_id}/tarefas")
    suspend fun getTarefas(@Path("estrutura_id") estruturaId: Int): List<Tarefa>

    @GET("api/atividades")
    suspend fun buscarAtividades(@Query("q") query: String?): List<Atividade>

    @POST("api/lancamento/poste")
    suspend fun lancarPoste(@Body request: LancamentoPosteRequest): ConstrucaoApiResponse

    @POST("api/lancamento/lote")
    suspend fun lancarLote(@Body request: LancamentoLoteRequest): ConstrucaoApiResponse
}

object ConstrucaoRetrofitClient {
    // Endereço local padrão para o emulador Android conectar ao localhost da máquina hospedeira
    private const val BASE_URL = "http://10.0.2.2:8000/"

    val instance: ConstrucaoApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ConstrucaoApiService::class.java)
    }
}
