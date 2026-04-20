// Módulo: app/src/main/java/com/chicoeletro/dds/data/sync/ContentLocalDataSource.kt
// Função: Abstração para o gerenciamento local de conteúdos de treinamento. Define a interface 
//         para identificação de itens pendentes e persistência do manifesto.
// Tecnologias: Kotlin Interface.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.data.sync

interface ContentLocalDataSource {
    suspend fun getPendingItems(remoteManifest: List<ManifestItem>): List<ManifestItem>
    suspend fun saveManifest(remoteManifest: List<ManifestItem>)
}