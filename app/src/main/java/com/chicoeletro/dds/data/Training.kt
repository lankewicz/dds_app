// Módulo: app/src/main/java/com/chicoeletro/dds/data/Training.kt
// Função: Entidade fundamental que representa um Treinamento (DDS). Define identificador 
//         único, data agendada e título descritivo do tema.
// Tecnologias: Kotlinx Serialization.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 07/06/2025: Criação inicial.

package com.chicoeletro.dds.data

import kotlinx.serialization.Serializable

@Serializable
data class Training(
    val id: String,
    val date: String,
    val title: String
)