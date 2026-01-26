// Módulo: app/src/main/java/com/example/dds/core/LastTeamData.kt
// Função: Representa os dados de última equipe/eletricistas a serem salvos no DataStore.
// Histórico de Alterações:
//   - 04/06/2025: Criação inicial.
//   - 12/06/2025: Adicionada anotação @Serializable para Kotlinx Serialization.

package com.chicoeletro.dds.core

import kotlinx.serialization.Serializable

@Serializable
data class LastTeamData(
    val equipe: String,
    val eletricistas: List<String>,
    // Se true, significa: "salvei local, mas ainda não confirmei write no Firestore"
    val pendingSync: Boolean = false,
    // Epoch millis do último sync concluído com sucesso
    val lastSyncedAt: Long? = null
)
