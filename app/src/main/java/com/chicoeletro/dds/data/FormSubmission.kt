package com.chicoeletro.dds.data

import kotlinx.serialization.Serializable

/**
 * Módulo: app/src/main/java/com/example/dds/data/FormSubmission.kt
 * Descrição: Data class que representa uma submissão de formulário de DDS,
 *            separando DataConclusao e HoraConclusao em campos distintos.
 * Autor: Valdinei Lankewicz
 * Data de Criação: 04/06/2025
 *
 * Histórico de Alterações:
 *   - 04/06/2025: Separados dataHora em dataConclusao e horaConclusao.
 */

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

    // ✅ Offline-first: caminhos locais (armazenamento privado do app)
    val localPhotoPath: String? = null,   // ex: /data/user/0/.../files/dds_....jpg
    val localThumbPath: String? = null,   // ex: /data/user/0/.../cache/thumb_....jpg

    // ✅ Controle de sync
    val syncStatus: String = "PENDING",   // PENDING | UPLOADING | SYNCED | ERROR
    val retryCount: Int = 0,
    val lastError: String? = null

)
