// Módulo: app/src/main/java/com/example/dds/data/ListaJson.kt
// Função: Data class para realizar a desserialização de 'lista.json'.
// Histórico de Alterações:
//   - 06/06/2025: Criado para representar o JSON que possui { "files": [ ... ] }.

package com.chicoeletro.dds.data

import kotlinx.serialization.Serializable

@Serializable
data class ListaJson(
    val files: List<String>
)
