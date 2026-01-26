// Módulo: app/src/main/java/com/example/dds/data/Training.kt
// Função: Representa um treinamento (id, data, título).
// Histórico de Alterações:
//   - 02/06/2025: Criação inicial.
//   - 06/06/2025: Adicionado @Serializable para permitir parse de JSON (se necessário).

package com.chicoeletro.dds.data

import kotlinx.serialization.Serializable

@Serializable
data class Training(
    val id: String,
    val date: String,
    val title: String
)
