// Módulo: app/src/main/java/com/chicoeletro/dds/data/sync/DataStoreLocalDataSource.kt
// Função: Implementação da fonte de dados local via sistema de arquivos. Gerencia a persistência 
//         do manifesto de sincronização e o controle de versionamento dos itens em cache.
// Tecnologias: Java File API, Kotlinx Serialization (JSON).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.data.sync

import android.content.Context
import kotlinx.serialization.json.Json
import java.io.File

class DataStoreLocalDataSource(
    private val context: Context
) : ContentLocalDataSource {

    private val manifestFile = File(context.filesDir, "manifest.json")

    override suspend fun getPendingItems(remoteManifest: List<ManifestItem>): List<ManifestItem> {
        if (!manifestFile.exists()) return remoteManifest
        val localManifest = Json.decodeFromString<List<ManifestItem>>(manifestFile.readText())
        return remoteManifest.filter { remote ->
            val local = localManifest.find { it.id == remote.id }
            local == null || local.version < remote.version
        }
    }

    override suspend fun saveManifest(remoteManifest: List<ManifestItem>) {
        val text = Json.encodeToString(remoteManifest)
        manifestFile.writeText(text)
    }
}