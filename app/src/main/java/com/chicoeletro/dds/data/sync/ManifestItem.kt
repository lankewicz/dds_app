// Módulo: app/src/main/java/com/example/dds/data/sync/ManifestItem.kt
// Gerado em: 17/06/2025
// Descrição: Modelo de cada item no manifest de conteúdos de treinamento.
// Histórico de Alterações:
// - 17/06/2025: Criação inicial.

package com.chicoeletro.dds.data.sync

import kotlinx.serialization.Serializable

@Serializable
data class ManifestItem(
    val id: String,
    val version: Long,
    val url: String,
    val hash: String
)
