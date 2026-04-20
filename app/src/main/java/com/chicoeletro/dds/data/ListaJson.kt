// Módulo: app/src/main/java/com/chicoeletro/dds/data/ListaJson.kt
// Função: Modelo de dados para o índice mestre de treinamentos (lista.json). Mapeia identificadores, 
//         nomes de arquivos e datas de agendamento disponíveis no servidor.
// Tecnologias: Kotlinx Serialization (JSON).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 06/06/2025: Criação inicial.

package com.chicoeletro.dds.data

import kotlinx.serialization.Serializable

@Serializable
data class ListaJson(
    val files: List<String>
)