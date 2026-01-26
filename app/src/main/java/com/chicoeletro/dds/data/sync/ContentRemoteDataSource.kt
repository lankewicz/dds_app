// Módulo: app/src/main/java/com/example/dds/data/sync/ContentRemoteDataSource.kt
// Gerado em: 17/06/2025
// Descrição: Interface para buscar manifest e baixar assets remotamente.
// Histórico de Alterações:
// - 17/06/2025: Criação inicial.

package com.chicoeletro.dds.data.sync

interface ContentRemoteDataSource {
    suspend fun fetchManifest(): List<ManifestItem>
    suspend fun downloadAndSave(item: ManifestItem)
}
