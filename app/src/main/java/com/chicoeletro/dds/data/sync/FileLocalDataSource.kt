// Módulo: app/src/main/java/com/example/dds/data/sync/FileLocalDataSource.kt
// Gerado em: 17/06/2025
// Descrição: Grava cada asset baixado em disco, organizando por pasta de treinamento.
// Histórico de Alterações:
// - 17/06/2025: Criação inicial.

package com.chicoeletro.dds.data.sync

import android.content.Context
import java.io.File

class FileLocalDataSource(
    private val context: Context
) : ContentLocalDataSource {
    fun trainingRoot(): File = File(context.filesDir, "trainings")
    fun trainingDir(id: String): File = File(trainingRoot(), id)

    override suspend fun getPendingItems(remoteManifest: List<ManifestItem>): List<ManifestItem> {
        // Delegate to DataStoreLocalDataSource for manifest diff
        return DataStoreLocalDataSource(context).getPendingItems(remoteManifest)
    }

    override suspend fun saveManifest(remoteManifest: List<ManifestItem>) {
        // Delegate manifest persistence
        DataStoreLocalDataSource(context).saveManifest(remoteManifest)
    }
}
