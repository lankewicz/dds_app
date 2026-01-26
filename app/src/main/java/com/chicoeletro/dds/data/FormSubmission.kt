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
@Serializable
data class FormSubmission(
    val equipe: String,
    val tema: String,
    val eletricistas: List<String>,
    val headerDate: String,
    val headerTitle: String,
    val trainingName: String,     // nome/id do treinamento
    val dataConclusao: String,
    val horaConclusao: String,
    val submittedAt: String
)
