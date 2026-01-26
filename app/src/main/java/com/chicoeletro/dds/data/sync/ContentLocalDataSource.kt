// Módulo: app/src/main/java/com/example/dds/data/sync/ContentLocalDataSource.kt
// Gerado em: 17/06/2025
// Descrição: Interface para comparar e persistir manifest localmente.
// Histórico de Alterações:
// - 17/06/2025: Criação inicial.

package com.chicoeletro.dds.data.sync

interface ContentLocalDataSource {
    suspend fun getPendingItems(remoteManifest: List<ManifestItem>): List<ManifestItem>
    suspend fun saveManifest(remoteManifest: List<ManifestItem>)
}
