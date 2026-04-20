// Módulo: app/src/main/java/com/chicoeletro/dds/data/FormSubmission.kt
// Função: Modelo de dados central para submissões de treinamentos. Gerencia o estado de 
//         conclusão (data, hora, duração), metadados da equipe e controle de sincronização.
// Tecnologias: Kotlinx Serialization, java.util.UUID.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 04/06/2025: Criação inicial.

package com.chicoeletro.dds.data

import kotlinx.serialization.Serializable


import java.util.UUID
@Serializable
data class FormSubmission(
    val submissionId: String = UUID.randomUUID().toString(),
    val equipe: String,
    val tema: String,
    val eletricistas: List<String>,
    val headerDate: String,
    val headerTitle: String,
    val trainingName: String,     // nome/id do treinamento
    val dataConclusao: String,
    val horaConclusao: String,
    val submittedAt: String,
    val duracao: String = "",

    // ✅ Offline-first: caminhos locais (armazenamento privado do app)
    val localPhotoPath: String? = null,   // ex: /data/user/0/.../files/dds_....jpg
    val localThumbPath: String? = null,   // ex: /data/user/0/.../cache/thumb_....jpg

    // ✅ Controle de sync
    val syncStatus: String = "PENDING",   // PENDING | UPLOADING | SYNCED | ERROR
    val retryCount: Int = 0,
    val lastError: String? = null

)