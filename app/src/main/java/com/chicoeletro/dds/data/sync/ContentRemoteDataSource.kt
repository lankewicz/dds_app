// Módulo: app/src/main/java/com/chicoeletro/dds/data/sync/ContentRemoteDataSource.kt
// Função: Abstração para o acesso remoto a recursos de treinamento. Define a interface para 
//         obtenção do manifesto mestre e download de arquivos da nuvem.
// Tecnologias: Kotlin Interface.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.data.sync

interface ContentRemoteDataSource {
    suspend fun fetchManifest(): List<ManifestItem>
    suspend fun downloadAndSave(item: ManifestItem)
}