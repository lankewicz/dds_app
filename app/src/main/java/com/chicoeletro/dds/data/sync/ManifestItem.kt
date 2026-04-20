// Módulo: app/src/main/java/com/chicoeletro/dds/data/sync/ManifestItem.kt
// Função: Modelo de dados para os itens representados no manifesto de sincronização. Contém 
//         metadados de versão e URL para controle granular do cache.
// Tecnologias: Kotlinx Serialization.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.data.sync

import kotlinx.serialization.Serializable

@Serializable
data class ManifestItem(
    val id: String,
    val version: Long,
    val url: String,
    val hash: String
)