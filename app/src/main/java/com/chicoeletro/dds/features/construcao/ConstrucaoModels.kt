// Módulo: app/src/main/java/com/chicoeletro/dds/features/construcao/ConstrucaoModels.kt
// Função: Modelos de dados para serialização/desserialização da API de Construção (Copel/Chico Eletro).
// Tecnologias: Kotlinx Serialization (compatível com Gson).
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.features.construcao

import kotlinx.serialization.Serializable

@Serializable
data class Projeto(
    val id: String,
    val titulo: String,
    val data_importacao: String
)

@Serializable
data class Estrutura(
    val id: Int,
    val projeto_id: String,
    val identificador: String,
    val tipo: String,
    val descricao_resumida: String? = null
)

@Serializable
data class Tarefa(
    val id: Int,
    val estrutura_id: Int,
    val atividade_codigo: Int,
    val quantidade: Double,
    val sinal: String,
    val descricao: String,
    val us_montagem: Double,
    val us_desmontagem: Double
)

@Serializable
data class Atividade(
    val codigo: Int,
    val descricao: String,
    val us_montagem: Double,
    val us_desmontagem: Double,
    val calculo_dinamico: Boolean? = false,
    val tipo_calculo: String? = null
)

@Serializable
data class LancamentoPosteRequest(
    val equipe_numero: Int,
    val data_execucao: String,
    val projeto_id: String,
    val estrutura_id: Int,
    val tarefas_completadas: List<Int>,
    val tarefas_quantidades: Map<String, Double>? = null
)

@Serializable
data class ItemLoteRequest(
    val codigo: Int,
    val quantidade: Double,
    val tipo: String,
    val elementos: Int? = null,
    val distancia: Double? = null,
    val horas: Double? = null
)

@Serializable
data class LancamentoLoteRequest(
    val equipe_numero: Int,
    val data_execucao: String,
    val projeto_id: String?,
    val itens: List<ItemLoteRequest>
)

@Serializable
data class ConstrucaoApiResponse(
    val sucesso: Boolean,
    val detail: String? = null,
    val mensagem: String? = null
)
