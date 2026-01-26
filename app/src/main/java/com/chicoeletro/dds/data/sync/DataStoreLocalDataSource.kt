// Módulo: app/src/main/java/com/example/dds/data/sync/DataStoreLocalDataSource.kt
// Gerado em: 17/06/2025
// Descrição: Implementa ContentLocalDataSource usando arquivo JSON em filesDir.
// Histórico de Alterações:
// - 17/06/2025: Criação inicial.

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
